import os.path
import re

from charmhelpers import fetch
from charmhelpers.contrib.charmsupport import nrpe
from charmhelpers.core import hookenv, host
from charmhelpers.core.hookenv import DEBUG, ERROR, WARNING
from distutils.version import LooseVersion


def local_plugins_dir():
    return '/usr/local/lib/nagios/plugins'


def has_cassandra_version(minimum_ver):
    cassandra_version = get_cassandra_version()
    assert cassandra_version is not None, 'Cassandra package not yet installed'
    return LooseVersion(cassandra_version) >= LooseVersion(minimum_ver)


def get_cassandra_edition():
    config = hookenv.config()
    edition = config['edition'].lower()
    if edition not in ('community', 'dse'):
        hookenv.log('Unknown edition {!r}. Using community.'.format(edition),
                    ERROR)
        edition = 'community'
    return edition


def get_cassandra_version():
    if get_cassandra_edition() == 'dse':
        dse_ver = get_package_version('dse-full')
        if not dse_ver:
            return None
        elif LooseVersion(dse_ver) >= LooseVersion('4.7'):
            return '2.1'
        else:
            return '2.0'
    return get_package_version('cassandra')


def get_package_version(package):
    cache = fetch.apt_cache()
    if package not in cache:
        return None
    pkgver = cache[package].current_ver
    if pkgver is not None:
        return pkgver.ver_str
    return None


def get_all_database_directories():
    config = hookenv.config()
    dirs = dict(
        data_file_directories=[get_database_directory(d)
                               for d in (config['data_file_directories'] or
                                         'data').split()],
        commitlog_directory=get_database_directory(
            config['commitlog_directory'] or 'commitlog'),
        saved_caches_directory=get_database_directory(
            config['saved_caches_directory'] or 'saved_caches'))
    if has_cassandra_version('3.0'):
        # Not yet configurable. Make configurable with Juju native storage.
        dirs['hints_directory'] = get_database_directory('hints')
    return dirs


def get_database_directory(config_path):
    '''Convert a database path from the service config to an absolute path.

    Entries in the config file may be absolute, relative to
    /var/lib/cassandra, or relative to the mountpoint.
    '''
    import relations
    storage = relations.StorageRelation()
    if storage.mountpoint:
        root = os.path.join(storage.mountpoint, 'cassandra')
    else:
        root = '/var/lib/cassandra'
    return os.path.join(root, config_path)


def nrpe_external_master_relation():
    ''' Configure the nrpe-external-master relation '''
    local_plugins = local_plugins_dir()
    if os.path.exists(local_plugins):
        src = os.path.join(hookenv.charm_dir(),
                           "files", "check_cassandra_heap.sh")
        with open(src, 'rb') as f:
            host.write_file(os.path.join(local_plugins,
                                         'check_cassandra_heap.sh'),
                            f.read(), perms=0o555)

    nrpe_compat = nrpe.NRPE()
    conf = hookenv.config()

    cassandra_heap_warn = conf.get('nagios_heapchk_warn_pct')
    cassandra_heap_crit = conf.get('nagios_heapchk_crit_pct')
    if cassandra_heap_warn and cassandra_heap_crit:
        nrpe_compat.add_check(
            shortname="cassandra_heap",
            description="Check Cassandra Heap",
            check_cmd="check_cassandra_heap.sh localhost {} {}"
                      "".format(cassandra_heap_warn, cassandra_heap_crit))

    cassandra_disk_warn = conf.get('nagios_disk_warn_pct')
    cassandra_disk_crit = conf.get('nagios_disk_crit_pct')
    dirs = get_all_database_directories()
    dirs = set(dirs['data_file_directories'] +
               [dirs['commitlog_directory'], dirs['saved_caches_directory']])
    for disk in dirs:
        check_name = re.sub('[^A-Za-z0-9_]', '_', disk)
        if cassandra_disk_warn and cassandra_disk_crit:
            shortname = "cassandra_disk{}".format(check_name)
            hookenv.log("Adding disk utilization check {}".format(shortname),
                        DEBUG)
            nrpe_compat.add_check(
                shortname=shortname,
                description="Check Cassandra Disk {}".format(disk),
                check_cmd="check_disk -u GB -w {}% -c {}% -K 5% -p {}"
                          "".format(cassandra_disk_warn, cassandra_disk_crit,
                                    disk))
    nrpe_compat.write()
