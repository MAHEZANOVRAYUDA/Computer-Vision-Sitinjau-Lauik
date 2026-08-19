import zipfile
import xml.etree.ElementTree as ET

def read_docx(file_path):
    z = zipfile.ZipFile(file_path)
    xml_content = z.read('word/document.xml')
    root = ET.fromstring(xml_content)
    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    texts = [node.text for node in root.findall('.//w:t', ns) if node.text]
    return '\n'.join(texts)

text = read_docx(r'e:\LPPM\sitinjau-lauik-cv\laporan dan data sitinjau lauik.docx')
with open('doc_content.txt', 'w', encoding='utf-8') as f:
    f.write(text)
