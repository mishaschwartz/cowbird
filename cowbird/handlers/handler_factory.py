import importlib
from typing import TYPE_CHECKING

from cowbird.config import get_all_configs
from cowbird.utils import SingletonMeta, get_config_path, get_logger, get_settings

if TYPE_CHECKING:
    from typing import List

    from cowbird.handlers.handler import Handler

LOGGER = get_logger(__name__)

VALID_HANDLERS = ["Catalog", "Geoserver", "Magpie", "Nginx", "Thredds",
                  "FileSystem"]


class HandlerFactory(metaclass=SingletonMeta):
    """
    Create handler instance using handler name.
    """

    def __init__(self):
        self.settings = get_settings(None, app=True)
        config_path = get_config_path()
        handlers_configs = get_all_configs(config_path, "handlers", allow_missing=True)
        self.handlers_cfg = {}
        for handlers_config in handlers_configs:
            if not handlers_config:
                LOGGER.warning("Handlers configuration is empty.")
                continue
            for name, cfg in handlers_config.items():
                if name in self.handlers_cfg:
                    LOGGER.warning("Ignoring a duplicate handler configuration for [%s].", name)
                else:
                    self.handlers_cfg[name] = cfg
        self.handlers = {}
        LOGGER.info("Handlers config : [%s]", ", ".join([f"{name} [{cfg.get('active', False)}]"
                                                         for name, cfg in self.handlers_cfg.items()]))

    def create_handler(self, name):
        # type: (HandlerFactory, str) -> Handler
        """
        Instantiates a new `Handler` implementation using its name, overwriting an existing instance if required.
        """
        handler = None
        if (name in VALID_HANDLERS and
                name in self.handlers_cfg and
                self.handlers_cfg[name].get("active", False)):
            module = importlib.import_module(".".join(["cowbird.handlers.impl", name.lower()]))
            cls = getattr(module, name)
            handler = cls(settings=self.settings, name=name, **self.handlers_cfg[name])
        self.handlers[name] = handler
        return handler

    def get_handler(self, name):
        # type: (HandlerFactory, str) -> Handler
        """
        Instantiates a `Handler` implementation using its name if it doesn't exist or else returns the existing one from
        cache.
        """
        try:
            return self.handlers[name]
        except KeyError:
            return self.create_handler(name)

    def get_active_handlers(self):
        # type: (HandlerFactory) -> List[Handler]
        """
        Return a sorted list by priority of `Handler` implementation activated in the config.
        """
        return sorted(filter(None, [self.get_handler(name) for name in self.handlers_cfg]),
                      key=lambda handler: handler.priority)
