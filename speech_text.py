"""Spoken text excludes parenthetical directions and markup."""
import re,unicodedata

def clean(value):
    value=unicodedata.normalize('NFC',value)
    # Chat laughter and isolated Korean consonants have no spoken word.
    value=re.sub(r'[\u3131-\u318e]+','',value)
    value=re.sub(r'```[\s\S]*?```','',value)
    value=re.sub(r'\[([^\]]+)\]\([^)]*\)',r'\1',value)
    output=[];stack=[];closing={'(':')','（':'）','[':']','【':'】'}
    for ch in value:
        if ch in closing:stack.append(closing[ch])
        elif stack:
            if ch==stack[-1]:stack.pop()
        else:output.append(ch)
    value=''.join(output)
    value=re.sub(r'(?<!\*)\*([^*\n]+)\*(?!\*)','',value)
    value=re.sub(r'https?://\S+','',value)
    return re.sub(r'\s+',' ',re.sub(r'[*#`_>]+','',value)).strip()
