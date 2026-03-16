from pathlib import Path
from typing import Iterator
import pandas as pd


def read_cur_file(path: Path, chunk_size: int = 500_000) -> Iterator[pd.DataFrame]:
    path = Path(path)
    if path.suffix == ".gz":
        for chunk in pd.read_csv(path, chunksize=chunk_size, dtype=str, compression="gzip"):
            yield chunk
    elif path.suffix in (".csv", ""):
        for chunk in pd.read_csv(path, chunksize=chunk_size, dtype=str):
            yield chunk
    elif path.suffix == ".parquet":
        yield pd.read_parquet(path, engine="pyarrow")
    else:
        # Try CSV as default
        for chunk in pd.read_csv(path, chunksize=chunk_size, dtype=str):
            yield chunk
