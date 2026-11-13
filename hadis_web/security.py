"""Reader HTTP boundary: loopback by default, explicit HTTPS origin in production."""
from urllib.parse import urlsplit

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from .config import normalize_public_origin


SECURITY_HEADERS={
    'Content-Security-Policy':"default-src 'none'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; style-src-attr 'unsafe-inline'; font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'",
    'X-Content-Type-Options':'nosniff',
    'X-Frame-Options':'DENY',
    'Referrer-Policy':'no-referrer',
    'Cross-Origin-Resource-Policy':'same-origin',
    'Permissions-Policy':'camera=(), microphone=(), geolocation=()',
}
LOOPBACK_HOSTS={'127.0.0.1','localhost','::1'}


def authority(value,scheme,allowed_hosts=LOOPBACK_HOSTS):
    if not value or any(c.isspace() or ord(c)<32 or ord(c)==127 or c in '/\\?#@%' for c in value):
        raise ValueError('Invalid authority')
    parsed=urlsplit(scheme+'://'+value)
    port=parsed.port
    if parsed.hostname not in allowed_hosts or (port is not None and not 1<=port<=65535):
        raise ValueError('Non-local authority')
    return scheme,parsed.hostname,port if port is not None else (443 if scheme=='https' else 80)


class LocalReaderSecurity:
    def __init__(self,app,public_origin=None):
        self.app=app
        self.expected=None
        self.allowed_hosts=LOOPBACK_HOSTS
        self.headers=dict(SECURITY_HEADERS)
        if public_origin:
            origin=urlsplit(normalize_public_origin(public_origin))
            self.allowed_hosts={origin.hostname}
            self.expected=authority(origin.netloc,'https',self.allowed_hosts)
            self.headers['Strict-Transport-Security']='max-age=31536000'

    async def __call__(self,scope,receive,send):
        if scope['type']!='http':
            return await self.app(scope,receive,send)

        async def protected_send(message):
            if message['type']=='http.response.start':
                headers=MutableHeaders(scope=message)
                headers.update(self.headers)
            await send(message)

        headers=Headers(scope=scope)
        hosts=headers.getlist('host')
        try:
            if len(hosts)!=1:raise ValueError('Ambiguous host')
            target=authority(hosts[0],'https' if self.expected else scope['scheme'],self.allowed_hosts)
            if self.expected and target!=self.expected:raise ValueError('Unexpected public authority')
        except ValueError:
            return await JSONResponse({'detail':'Geçersiz sunucu adresi.'},status_code=400)(scope,receive,protected_send)
        origins=headers.getlist('origin')
        if origins:
            try:
                if len(origins)!=1:raise ValueError('Ambiguous origin')
                origin=urlsplit(origins[0])
                if origin.scheme not in ('http','https') or origin.path or origin.query or origin.fragment:
                    raise ValueError('Invalid origin')
                if authority(origin.netloc,origin.scheme,self.allowed_hosts)!=target:raise ValueError('Foreign origin')
            except ValueError:
                return await JSONResponse({'detail':'Bu kaynaktan yerel API erişimine izin verilmiyor.'},status_code=403)(scope,receive,protected_send)
        if scope['path'].startswith('/api/') and headers.get('sec-fetch-site') in ('cross-site','same-site'):
            return await JSONResponse({'detail':'Yerel API yalnız aynı sayfadan kullanılabilir.'},status_code=403)(scope,receive,protected_send)
        if len(scope.get('query_string',b''))>4096:
            return await JSONResponse({'detail':'İstek adresi çok uzun.'},status_code=414)(scope,receive,protected_send)
        await self.app(scope,receive,protected_send)
