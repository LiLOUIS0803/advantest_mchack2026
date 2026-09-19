"""Shared definitions used by fitting, streaming decisions and charts."""
import numpy as np

FORMAL_LABELS = {
    'low_yield': 'Low yield which yield is low than 80',
    'mean_trend_up': 'Mean Trend Up', 'mean_trend_down': 'Mean Trend Down',
    'stdev_trend_up': 'Stdev Trend Up', 'stdev_trend_down': 'Stdev Trend Down',
}


def window_statistics(block, scale):
    """16 observations on axis 0; sample SD uses ddof=1, without clipping."""
    block = np.asarray(block, dtype=float)
    if block.shape[0] != 16:
        raise ValueError('Expected 16 observations')
    previous, current = block[:8], block[8:]
    before_mean, after_mean = previous.mean(axis=0), current.mean(axis=0)
    before_std, after_std = previous.std(axis=0, ddof=1), current.std(axis=0, ddof=1)
    # Scale-aware floor handles constant windows without infinite JSON values.
    floor = np.maximum(np.asarray(scale)*1e-6, 1e-12)
    ratio = np.maximum(after_std, floor)/np.maximum(before_std, floor)
    return {'delta': (after_mean-before_mean)/scale, 'spread': ratio,
            'before_mean': before_mean, 'after_mean': after_mean,
            'before_std': before_std, 'after_std': after_std}
