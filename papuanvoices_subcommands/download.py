"""
dl
"""
import urllib.request

from lexibank_papuanvoices import Dataset

C = 0


def maybe_download(row, d):
    global C
    path = d / row['Name']
    if (path.exists() and path.stat().st_size != int(row['size'])) or not path.exists():
        C += 1
        url = f'https://cdstar.eva.mpg.de/bitstreams/{row["objid"]}/{row["Name"]}'
        if C % 20 == 0:
            print(url)
        urllib.request.urlretrieve(url, path)


def run(args):
    ds = Dataset()
    for row in ds.cldf_reader().iter_rows('MediaTable'):
        maybe_download(row, ds.raw_dir / 'media')
