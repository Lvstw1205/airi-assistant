"""Single byte ranges for Safari's local motion video decoder."""
import re

def byte_range(value, size):
    if not value:return 0,size-1,False
    match=re.fullmatch(r'bytes=(\d*)-(\d*)',value.strip())
    if not match or not any(match.groups()):raise ValueError('Unsupported byte range')
    first,last=match.groups()
    if not first:
        count=int(last)
        if count<=0:raise ValueError('Empty byte range')
        return max(0,size-count),size-1,True
    start=int(first);end=min(int(last),size-1) if last else size-1
    if start>=size or start>end:raise ValueError('Unsatisfiable byte range')
    return start,end,True
