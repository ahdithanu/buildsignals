"""Convert a pinned public Census cartographic asset, not product inventory.

Requires optional conversion tool pyshp==2.3.1. No network or application DB.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
from zipfile import ZipFile

import shapefile

SOURCE_SHA256 = '95902e4cda23f5f403e576d1bcd0e54a0f453d9b81893b080f4c15029302e348'
STATES = frozenset('AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY'.split())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    content = args.source.read_bytes()
    if hashlib.sha256(content).hexdigest() != SOURCE_SHA256:
        raise ValueError('Census source archive hash mismatch')
    with ZipFile(io.BytesIO(content)) as archive:
        stem = 'cb_2018_us_state_20m'
        reader = shapefile.Reader(shp=io.BytesIO(archive.read(stem + '.shp')),
                                  shx=io.BytesIO(archive.read(stem + '.shx')),
                                  dbf=io.BytesIO(archive.read(stem + '.dbf')))
        features = []
        for item in reader.iterShapeRecords():
            record = item.record.as_dict()
            if record['STUSPS'] in STATES:
                features.append(dict(type='Feature', properties=dict(code=record['STUSPS'], name=record['NAME']),
                                     geometry=item.shape.__geo_interface__))
    if len(features) != 51 or {item['properties']['code'] for item in features} != STATES:
        raise ValueError('Expected all 50 states plus DC exactly once')
    features.sort(key=lambda item: item['properties']['code'])
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    args.destination.write_text(json.dumps(dict(type='FeatureCollection', features=features),
                                           separators=(',', ':'), allow_nan=False) + '\n')
    print(f'Converted {len(features)} Census state outlines; no activity values or inventory added')


if __name__ == '__main__':
    main()
