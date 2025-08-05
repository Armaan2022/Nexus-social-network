# social/templatetags/markdownify.py
from django import template
import markdown
import re
from markdown.extensions.extra import ExtraExtension

register = template.Library()

class ImageExtractor(markdown.Extension):
    def extendMarkdown(self, md):
        md.inlinePatterns.register(ImagePattern(r'!\[(.*?)\]\((.*?)\)', md), 'image', 175)

class ImagePattern(markdown.inlinepatterns.InlineProcessor):
    def handleMatch(self, m, data):
        alt_text = m.group(1) or ''
        src = m.group(2).strip()
        
        # Create the image element
        el = markdown.util.etree.Element('img')
        el.set('src', src)
        el.set('alt', alt_text)
        el.set('class', 'img-fluid rounded shadow-sm')
        
        return el, m.start(0), m.end(0)

@register.filter
def markdownify(text):
    # Return empty string for None
    if text is None:
        return ''
    
    return markdown.markdown(text, extensions=[
        'extra', 'nl2br', 'sane_lists', ImageExtractor()
    ])

@register.filter
def split(value, arg):
    """
    Splits a string on the given delimiter.
    """
    return value.split(arg)