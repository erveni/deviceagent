"""Deterministic, platform-balanced ordering for ranking retries."""
import random


def mixed_platform_order(specs,seed):
    """Shuffle within platforms, then interleave every nonempty platform.

    Pure random shuffling can accidentally create a long single-platform prefix.
    This keeps each three-job band mixed while still randomizing platform order and
    the keywords selected within every platform.
    """
    groups={}
    for spec in specs:groups.setdefault(spec[2].lower(),[]).append(spec)
    rng=random.Random(seed)
    for values in groups.values():rng.shuffle(values)
    platforms=list(groups);rng.shuffle(platforms)
    result=[]
    while any(groups.values()):
        cycle=[platform for platform in platforms if groups[platform]]
        rng.shuffle(cycle)
        for platform in cycle:result.append(groups[platform].pop())
    return result
