# Copyright (C) 2014 SUSE Linux Products GmbH
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

from datetime import datetime
import fcntl
from functools import wraps
import os
import shelve
try:
    import cPickle as pickle
except:
    import pickle


from xdg.BaseDirectory import save_cache_path
# Where the cache files are stored
CACHEDIR = save_cache_path('opensuse-repo-checker')


def memoize(ttl=None, session=False):
    """Decorator function to implement a persistent cache.

    >>> @memoize()
    ... def test_func(a):
    ...     return a

    Internally, the memoized function has a cache:

    >>> cache = [c.cell_contents for c in test_func.func_closure if 'sync' in dir(c.cell_contents)][0]
    >>> 'sync' in dir(cache)
    True

    There is a limit of the size of the cache

    >>> for k in cache:
    ...     del cache[k]
    >>> len(cache)
    0

    >>> for i in range(4095):
    ...     test_func(i)
    ... len(cache)
    4095

    >>> test_func(0)
    0

    >>> len(cache)
    4095

    >>> test_func(4095)
    4095

    >>> len(cache)
    3072

    >>> test_func(0)
    0

    >>> len(cache)
    3073

    >>> from datetime import timedelta
    >>> k = [k for k in cache if cPickle.loads(k) == ((0,), {})][0]
    >>> t, v = cache[k]
    >>> t = t - timedelta(days=10)
    >>> cache[k] = (t, v)
    >>> test_func(0)
    0
    >>> t2, v = cache[k]
    >>> t != t2
    True

    """

    # Configuration variables
    SLOTS = 4096            # Number of slots in the cache file
    NCLEAN = 1024           # Number of slots to remove when limit reached
    TIMEOUT = 60*60*2       # Time to live for every cache slot (seconds)

    # The session cache is only used when 'session' is True
    session_cache = {}

    def _memoize(fn):
        # Implement a POSIX lock / unlock extension for shelves. Inspired
        # on ActiveState Code recipe #576591
        def _lock(filename):
            lckfile = open(filename + '.lck', 'w')
            fcntl.flock(lckfile.fileno(), fcntl.LOCK_EX)
            return lckfile

        def _unlock(lckfile):
            fcntl.flock(lckfile.fileno(), fcntl.LOCK_UN)
            lckfile.close()

        def _open_cache(cache_name):
            cache = session_cache
            if not session:
                lckfile = _lock(cache_name)
                cache = shelve.open(cache_name, protocol=-1)
                # Store a reference to the lckfile to avoid to be
                # closed by gc
                cache.lckfile = lckfile
            return cache

        def _close_cache(cache):
            if not session:
                cache.close()
                _unlock(cache.lckfile)

        def _clean_cache(cache):
            len_cache = len(cache)
            if len_cache >= SLOTS:
                nclean = NCLEAN + len_cache - SLOTS
                keys_to_delete = sorted(cache, key=lambda k: cache[k][0])[:nclean]
                for key in keys_to_delete:
                    del cache[key]

        @wraps(fn)
        def _fn(*args, **kwargs):
            def total_seconds(td):
                return (td.microseconds + (td.seconds + td.days * 24 * 3600.) * 10**6) / 10**6
            now = datetime.now()
            key = pickle.dumps((args, kwargs), protocol=-1)
            updated = False
            cache = _open_cache(cache_name)
            if key in cache:
                timestamp, value = cache[key]
                updated = True if total_seconds(now-timestamp) < ttl else False
            if not updated:
                value = fn(*args, **kwargs)
                cache[key] = (now, value)
            _clean_cache(cache)
            _close_cache(cache)
            return value

        cache_dir = os.path.expanduser(CACHEDIR)
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
        cache_name = os.path.join(cache_dir, fn.__name__)
        return _fn

    ttl = ttl if ttl else TIMEOUT
    return _memoize
