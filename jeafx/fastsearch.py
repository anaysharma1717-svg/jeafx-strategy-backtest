"""Find the first index >= start where arr <op> val, scanning in growing chunks.
Same answer as np.nonzero(arr[start:] <op> val)[0][0] + start, but fast when the hit is near `start`
(important on long 3-minute series). Returns len(arr) if there is no hit."""
import numpy as np

_OPS = {"<=": np.less_equal, ">=": np.greater_equal, "<": np.less, ">": np.greater}


def first_index(arr: np.ndarray, start: int, op: str, val: float) -> int:
    f = _OPS[op]
    n = len(arr)
    chunk = 256
    while start < n:
        seg = arr[start:start + chunk]
        hit = np.nonzero(f(seg, val))[0]
        if len(hit):
            return start + int(hit[0])
        start += chunk
        chunk = min(chunk * 4, 1 << 20)
    return n
