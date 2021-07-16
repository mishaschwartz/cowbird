from collections import defaultdict
from typing import TYPE_CHECKING

from cowbird.monitoring.monitor import Monitor, MonitorException
from cowbird.database import get_db
from cowbird.database.stores import MonitoringStore
from cowbird.utils import SingletonMeta, get_logger

if TYPE_CHECKING:
    from cowbird.monitoring.fsmonitor import FSMonitor

LOGGER = get_logger(__name__)


class Monitoring(metaclass=SingletonMeta):
    """
    Class handling file system monitoring and registering listeners.

    .. todo:: At some point we will need a consistency function that goes through all monitored folder and make sure
              that monitoring services are up to date.
    """

    def __init__(self, config):
        self.monitors = defaultdict(lambda: {})
        self.store = get_db(config).get_store(MonitoringStore)

    def start(self):
        """
        Load existing monitors and start the monitoring
        """
        monitors = self.store.list_monitors()
        for mon in monitors:
            self.monitors[mon.path][mon.callback] = mon
            mon.start()

    def register(self, path, recursive, cb_monitor):
        # type: (str, bool, Union[FSMonitor, Type[FSMonitor], str]) -> Monitor
        """
        Register a monitor for a specific path and start it.

        @param path: Path to monitor
        @param recursive: Monitor subdirectory recursively?
        @param cb_monitor: FSMonitor for which an instance is created and events are sent
                           Can be an object, a class type implementing FSMonitor or a string containing module and class
                           name.
        """
        try:
            callback = Monitor.get_qualified_class_name(Monitor.get_fsmonitor_instance(cb_monitor))
            return self.monitors[path][callback]
        except KeyError:
            # Doesn't already exist
            try:
                mon = Monitor(path, recursive, cb_monitor)
                mon.start()
                self.monitors[mon.path][mon.callback] = mon
                self.store.save_monitor(mon)
                return mon
            except MonitorException as e:
                LOGGER.warning("Failed to start monitoring the following path [%s] with this monitor [%s] : [%s]",
                               path, callback, e)
        return None

    def unregister(self, path, cb_monitor):
        # type: (str, Union[FSMonitor, Type[FSMonitor], str]) -> bool
        """
        Stop a monitor and unregister it.

        @param path: Path used by the monitor
        @param cb_monitor: FSMonitor object to remove
                           Can be an object, a class type implementing FSMonitor or a string containing module and class
                           name.
        @return: True if the monitor is found and successfully stopped, False otherwise
        """
        if path in self.monitors:
            try:
                mon_qualname = Monitor.get_qualified_class_name(Monitor.get_fsmonitor_instance(cb_monitor))
                mon = self.monitors[path].pop(mon_qualname)
                if len(self.monitors[path]) == 0:
                    self.monitors.pop(path)
                mon.stop()
                self.store.delete_monitor(mon)
                return True
            except KeyError:
                pass
        return False
