"""Remove embedded personal PNG output paths from uncompressed Blender scenes.

Only NUL-terminated PNG paths in Scene blocks are changed. Block headers, sizes,
pointer addresses, DNA and all remaining bytes stay identical. No Blender scene
execution or saving of a user's open file is performed.
"""
import argparse
import re
import struct
from pathlib import Path


def sanitize(data):
    if data[:7]!=b'BLENDER' or data[7:9] not in (b'-v',b'_v',b'-V',b'_V'):
        raise ValueError('Expected an uncompressed Blender container')
    endian='<' if data[8:9]==b'v' else '>'
    ptr=8 if data[7:8]==b'-' else 4
    header=struct.Struct(endian+('4siQii' if ptr==8 else '4siIii'))
    result=bytearray(data);offset=12;changed=0
    while offset<len(data):
        code,size,address,dna,count=header.unpack_from(data,offset)
        start=offset+header.size;end=start+size
        if size<0 or end>len(data):raise ValueError('Invalid Blender block length')
        if code.rstrip(b'\0')==b'SC':
            block=data[start:end]
            for match in re.finditer(rb'(?<=\x00)(?:/Users/|/home/|[A-Z]:[\\/]Users[\\/])[^\x00\r\n]{1,1000}\.png(?=\x00)',block):
                replacement=b'//preview.png'
                if len(replacement)>len(match.group()):raise ValueError('Output field too short')
                result[start+match.start():start+match.end()]=replacement.ljust(len(match.group()),b'\0')
                changed+=1
        offset=end
        if code==b'ENDB':break
    if offset!=len(data):raise ValueError('Unexpected trailing container data')
    return bytes(result),changed


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('paths',nargs='+')
    for filename in parser.parse_args().paths:
        path=Path(filename);clean,count=sanitize(path.read_bytes())
        if count:path.write_bytes(clean)
        print(path.as_posix()+': '+str(count)+' private output paths removed')
