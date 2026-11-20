"""Keep bundled Qt/Python libraries out of externally installed programs."""

import os
import sys


def host_process_environment() -> dict[str, str]:
    environment = dict(os.environ)
    if getattr(sys, 'frozen', False) and sys.platform.startswith('linux'):
        original = environment.get('LD_LIBRARY_PATH_ORIG')
        if original:
            environment['LD_LIBRARY_PATH'] = original
        else:
            environment.pop('LD_LIBRARY_PATH', None)
        for variable in ('QT_PLUGIN_PATH', 'QT_QPA_PLATFORM_PLUGIN_PATH'):
            environment.pop(variable, None)
    return environment
