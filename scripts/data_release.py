"""Versioned, hash-verified data packages; original datastores are never modified."""
import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path,PurePosixPath
import re
import tarfile
import tempfile
import shutil
import sys
import errno
import ctypes


BLOCK=1024*1024


def logical_path(name):
    if not isinstance(name,str) or not name or '\\' in name or ':' in name or any(ord(c)<32 or ord(c)==127 for c in name):
        raise ValueError('Geçersiz paket yolu.')
    path=PurePosixPath(name)
    if path.is_absolute() or any(part in ('','..','.') for part in name.split('/')):
        raise ValueError('Paket yolu hedefin dışında olamaz.')
    for part in path.parts:
        if part.endswith((' ','.')) or re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])',part.split('.')[0],re.IGNORECASE):
            raise ValueError('Paket yolu Windows üzerinde güvenli değil.')
    return path


class SplitWriter:
    def __init__(self,folder,limit):
        self.folder,self.limit=folder,limit
        self.stream=None;self.parts=[];self.digest=hashlib.sha256();self.total=0

    def _close_part(self):
        if self.stream is not None:
            self.stream.close()
            self.parts.append({'name':self.name,'bytes':self.size,'sha256':self.part_digest.hexdigest()})
            self.stream=None

    def write(self,data):
        length=len(data);view=memoryview(data)
        while view:
            if self.stream is None:
                self.name=f'workspace.tar.gz.part{len(self.parts)+1:03d}'
                self.stream=(self.folder/self.name).open('xb');self.size=0;self.part_digest=hashlib.sha256()
            count=min(len(view),self.limit-self.size);chunk=view[:count]
            self.stream.write(chunk);self.digest.update(chunk);self.part_digest.update(chunk)
            self.total+=count;self.size+=count;view=view[count:]
            if self.size==self.limit:self._close_part()
        return length

    def flush(self):
        if self.stream:self.stream.flush()

    def close(self):self._close_part()


class HashReader:
    def __init__(self,stream):self.stream=stream;self.digest=hashlib.sha256();self.size=0
    def read(self,size):
        data=self.stream.read(size);self.digest.update(data);self.size+=len(data);return data


def build_bundle(sources,output,*,part_size=1024**3,version='0.1.0',metadata=None,progress=None):
    if not sources or not 1<=part_size<=1024**3:raise ValueError('Paket boyutu veya kaynak listesi geçersiz.')
    names=set()
    for name,source in sources.items():
        logical_path(name)
        if name.casefold() in names or Path(source).is_symlink() or not Path(source).is_file():
            raise ValueError('Tekrarlanan veya geçersiz kaynak dosyası.')
        names.add(name.casefold())
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    writer=SplitWriter(output,part_size);files=[]
    try:
        with gzip.GzipFile(fileobj=writer,mode='wb',filename='',compresslevel=3,mtime=0) as compressed:
            with tarfile.open(fileobj=compressed,mode='w|',format=tarfile.PAX_FORMAT) as archive:
                for name,source in sorted(sources.items()):
                    source=Path(source);before=source.stat()
                    if progress:progress(name,before.st_size)
                    info=tarfile.TarInfo(name);info.size=before.st_size;info.mode=0o644;info.mtime=0
                    with source.open('rb') as stream:
                        reader=HashReader(stream);archive.addfile(info,reader)
                    after=source.stat()
                    if reader.size!=before.st_size or (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
                        raise ValueError('Kaynak paketleme sırasında değişti.')
                    files.append({'path':name,'bytes':reader.size,'sha256':reader.digest.hexdigest()})
    finally:writer.close()
    manifest={'schema_version':1,'version':version,'files':files,
              'archive':{'format':'tar+gzip','bytes':writer.total,'sha256':writer.digest.hexdigest(),'parts':writer.parts}}
    if metadata:manifest['database']=metadata
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return manifest


class PartsReader(io.RawIOBase):
    def __init__(self,paths):self.paths=iter(paths);self.stream=None;super().__init__()
    def readable(self):return True
    def readinto(self,buffer):
        while True:
            if self.stream is None:
                path=next(self.paths,None)
                if path is None:return 0
                self.stream=path.open('rb')
            count=self.stream.readinto(buffer)
            if count:return count
            self.stream.close();self.stream=None
    def close(self):
        if self.stream:self.stream.close()
        super().close()


def publish_directory(source,destination):
    """Atomic no-replace publication; never fall back to POSIX replacing rename."""
    if os.name=='nt':
        os.rename(source,destination)
        return
    if not sys.platform.startswith('linux'):
        raise OSError(errno.ENOTSUP,'Atomik, üzerine yazmayan dizin yayını bu platformda desteklenmiyor.')
    library=ctypes.CDLL(None,use_errno=True)
    function=getattr(library,'renameat2',None)
    if function is None:raise OSError(errno.ENOTSUP,'renameat2 desteği gereklidir.')
    function.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]
    function.restype=ctypes.c_int
    if function(-100,os.fsencode(source),-100,os.fsencode(destination),1)!=0:
        code=ctypes.get_errno()
        raise OSError(code,os.strerror(code),str(destination))


def restore_bundle(manifest_path,destination,*,max_unpacked=32*1024**3):
    manifest_path=Path(manifest_path).resolve();destination=Path(destination).absolute()
    if destination.exists() or destination.is_symlink():raise FileExistsError('Hedef zaten var; üzerine yazılmadı.')
    if manifest_path.stat().st_size>8*1024**2:raise ValueError('Paket manifesti çok büyük.')
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest.get('schema_version')!=1 or manifest.get('archive',{}).get('format')!='tar+gzip':
        raise ValueError('Paket biçimi desteklenmiyor.')
    expected={};case_names=set();total=0
    if not 1<=len(manifest['files'])<=100000:raise ValueError('Dosya listesi geçersiz.')
    for entry in manifest['files']:
        name=entry['path'];logical_path(name)
        if name.casefold() in case_names or type(entry['bytes']) is not int or entry['bytes']<0:
            raise ValueError('Manifestte tekrarlanan veya geçersiz dosya.')
        expected[name]=entry;case_names.add(name.casefold());total+=entry['bytes']
    if total>max_unpacked:raise ValueError('Açılacak veri boyutu sınırı aşıldı.')
    paths=[];whole=hashlib.sha256();compressed_size=0
    parts=manifest['archive']['parts']
    if not 1<=len(parts)<=128:raise ValueError('Parça listesi geçersiz.')
    for index,entry in enumerate(parts,1):
        if entry['name']!=f'workspace.tar.gz.part{index:03d}':raise ValueError('Parça yolu veya sırası geçersiz.')
        path=manifest_path.parent/entry['name']
        if path.is_symlink() or not path.is_file() or path.stat().st_size!=entry['bytes']:
            raise ValueError('Paket parçası eksik veya değiştirilmiş; sürüm eklerindeki iki veri parçasını indirin.')
        digest=hashlib.sha256()
        with path.open('rb') as stream:
            while chunk:=stream.read(BLOCK):digest.update(chunk);whole.update(chunk);compressed_size+=len(chunk)
        if digest.hexdigest()!=entry['sha256']:raise ValueError('Parça hash doğrulaması başarısız.')
        paths.append(path)
    if compressed_size!=manifest['archive']['bytes'] or whole.hexdigest()!=manifest['archive']['sha256']:
        raise ValueError('Paket hash doğrulaması başarısız.')
    parent=destination.parent.resolve();parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.cevami-restore-',dir=parent)).resolve()
    if stage.parent!=parent:raise ValueError('Geçici hedef sınırı doğrulanamadı.')
    try:
        seen=set()
        with PartsReader(paths) as raw,io.BufferedReader(raw) as joined,gzip.GzipFile(fileobj=joined) as compressed:
            with tarfile.open(fileobj=compressed,mode='r|') as archive:
                for member in archive:
                    name=member.name;logical_path(name)
                    if not member.isfile() or name in seen or name not in expected or member.size!=expected[name]['bytes']:
                        raise ValueError('Arşiv üyesi manifestle uyuşmuyor veya güvenli değil.')
                    target=(stage/name).resolve()
                    if not target.is_relative_to(stage):raise ValueError('Arşiv yolu güvenli hedefin dışında.')
                    target.parent.mkdir(parents=True,exist_ok=True);digest=hashlib.sha256()
                    for parent_dir in target.parents:
                        if parent_dir==stage:break
                        parent_dir.chmod(0o755)
                    with archive.extractfile(member) as source,target.open('xb') as output:
                        while chunk:=source.read(BLOCK):digest.update(chunk);output.write(chunk)
                    if digest.hexdigest()!=expected[name]['sha256']:raise ValueError('Açılan dosyanın hash değeri farklı.')
                    target.chmod(0o644)
                    seen.add(name)
        if seen!=set(expected):raise ValueError('Arşivde eksik dosya var.')
        if destination.exists() or destination.is_symlink():raise FileExistsError('Hedef sonradan oluşturulmuş; üzerine yazılmadı.')
        if destination.parent.resolve()!=parent:raise ValueError('Hedef üst dizini değişti.')
        # The verified bundle contains published data, not credentials. A bind
        # mount must remain readable by the application's distinct UID 10001.
        stage.chmod(0o755)
        publish_directory(stage,destination)
    finally:
        if stage.exists():
            if stage.parent!=parent or not stage.name.startswith('.cevami-restore-'):raise ValueError('Geçici hedef temizliği reddedildi.')
            shutil.rmtree(stage)
    return manifest


def runtime_sources(settings,working_dump,working_report):
    root=settings.project_root
    sources={'references/datasets/jawami3_alkalem/jawami.db':settings.source_db,
        'references/datasets/jawami3_alkalem/verification.json':root/'references/datasets/jawami3_alkalem/verification.json',
        'search/search.sqlite':settings.search_db,
        'research/turkish-sources/translation-research.sqlite':settings.research_db,
        'GK4.5/GK4.5/Data/Books.zip':settings.books_archive,
        'postgres/working.dump':Path(working_dump),'postgres/working-export.json':Path(working_report)}
    for relative in ('references/turkish/fawazahmed0','references/search/fawazahmed0-20261104','references/turkish/hadeethenc-20261104'):
        folder=root/relative
        for path in folder.rglob('*'):
            if path.is_file() and path.suffix.lower() in ('.json','.sqlite','.md'):
                sources[path.relative_to(root).as_posix()]=path
    return sources


def main():
    parser=argparse.ArgumentParser(description='Hash doğrulamalı sürümlü veri paketi')
    sub=parser.add_subparsers(dest='command',required=True)
    build=sub.add_parser('build');build.add_argument('--output',required=True);build.add_argument('--working-dump',required=True);build.add_argument('--working-report',required=True)
    restore=sub.add_parser('restore');restore.add_argument('--manifest',required=True);restore.add_argument('--destination',required=True)
    args=parser.parse_args()
    if args.command=='restore':
        result=restore_bundle(args.manifest,args.destination)
        print(f"Doğrulanıp açıldı: {len(result['files'])} dosya.")
    else:
        from hadis_web.config import Settings
        settings=Settings.load();report=json.loads(Path(args.working_report).read_text(encoding='utf-8'))
        result=build_bundle(runtime_sources(settings,args.working_dump,args.working_report),args.output,
            metadata=report,progress=lambda name,size:print(f'Packaging {name} ({size} bytes)',flush=True))
        primary=next(row for row in result['files'] if row['path']=='references/datasets/jawami3_alkalem/jawami.db')
        expected=json.loads((settings.project_root/'references/datasets/jawami3_alkalem/verification.json').read_text())['database_sha256']
        if primary['sha256']!=expected:raise ValueError('Kaynak DB sabit manifestle uyuşmuyor; yüklemeyin.')
        print(f"Ready: {len(result['files'])} files, {len(result['archive']['parts'])} parts, {result['archive']['bytes']} compressed bytes.",flush=True)


if __name__=='__main__':main()
