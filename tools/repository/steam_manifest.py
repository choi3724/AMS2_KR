"""Read the plaintext Steam depot file table with bounded protobuf parsing."""
import struct


def varint(data, at):
    value = 0
    for shift in range(0, 64, 7):
        if at >= len(data):
            break
        byte = data[at]
        at += 1
        if shift == 63 and byte > 1:
            break
        value |= (byte & 127) << shift
        if not byte & 128:
            return value, at
    raise ValueError('Invalid protobuf varint')


def fields(data):
    at = 0
    while at < len(data):
        tag, at = varint(data, at)
        number, wire = tag >> 3, tag & 7
        if not number:
            raise ValueError('Invalid protobuf field')
        if wire == 0:
            value, at = varint(data, at)
        else:
            if wire == 2:
                length, at = varint(data, at)
            elif wire in (1, 5):
                length = {1: 8, 5: 4}[wire]
            else:
                raise ValueError('Unsupported protobuf wire type')
            if length > len(data) - at:
                raise ValueError('Truncated protobuf field')
            value = data[at:at + length]
            at += length
        yield number, wire, value


def parse_manifest(path):
    data = path.read_bytes()
    if len(data) < 8:
        raise ValueError('Truncated depot manifest')
    magic, length = struct.unpack_from('<II', data)
    if magic != 0x71F617D0 or length > len(data) - 8:
        raise ValueError('Unsupported depot manifest')
    result = []
    for number, wire, entry in fields(data[8:8 + length]):
        if (number, wire) != (1, 2):
            continue
        row = {}
        for field, kind, value in fields(entry):
            if (field, kind) == (1, 2):
                row['filename'] = value.decode('utf-8')
            elif (field, kind) == (2, 0):
                row['size'] = value
            elif (field, kind) == (5, 2):
                row['sha1_content'] = value.hex().upper()
        if 'filename' in row:
            result.append(row)
    return result
