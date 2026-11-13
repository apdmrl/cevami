"""Turkish renderings of source terms; these never recalculate a grade."""
SOURCE_NAME = 'Cevâmiu’l-Kelim 4.5'
GRADE_LABELS = {-1:'غير محدد',0:'صحيح',1:'حسن',2:'ضعيف',3:'شديد الضعف',4:'متهم بالوضع',5:'موضوع'}
GRADE_TURKISH = {-1:'Belirtilmemiş',0:'Sahih',1:'Hasen',2:'Zayıf',3:'Çok zayıf',4:'Uydurmakla itham edilmiş',5:'Mevzû (uydurma)'}
MARKER_TURKISH = {30000:'İnkıtâ yeri',30001:'Ta‘lîk yeri',30002:'İrsâl yeri'}
MARKER_SOURCES = {30000:'https://islamansiklopedisi.org.tr/munkati',
                  30001:'https://islamansiklopedisi.org.tr/muallak',
                  30002:'https://islamansiklopedisi.org.tr/mursel'}


def source_judgement(code):
    return {'code':code,'label':GRADE_LABELS.get(code,'غير محدد'),
            'label_tr':GRADE_TURKISH.get(code,'Belirtilmemiş'),'source':SOURCE_NAME,
            'translation_note':'Kaynak hükmünün Türkçe karşılığı; uygulamanın yeni değerlendirmesi değildir.',
            'translation_sources':['https://islamansiklopedisi.org.tr/hadis']}
