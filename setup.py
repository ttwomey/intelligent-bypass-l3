try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

config = {
    'name': 'intelligent-bypass-l3',
    'description': 'Monitor paths with BFD and heartbeat probes.  Disable '
                   ' failed paths and produce notifications.',
    'author': 'Arista EOS+ Consulting Services',
    'author_email': 'eosplus-dev@arista.com',
    'url': '://github.com/arista-eosplus/Intelligent-Bypass-L3',
    'download_url':
    'https://github.com/arista-eosplus/Intelligent-Bypass-L3/releases',
    'license': open('LICENSE').read().strip(),
    'version': open('VERSION').read().strip(),
    'scripts': ['hbm_service', 'hbm.py', 'bfd_int_sync.py'],
    'data_files': [('/mnt/flash', ['bfd_int_sync.ini'])],
}

setup(**config)
