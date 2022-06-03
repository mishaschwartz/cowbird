#!/usr/bin/env python
# coding: utf-8

"""
Cowbird is a middleware that manages interactions between various birds of the bird-house stack.
"""
import sys

from cowbird.config import (
    get_all_configs,
    validate_services_config_schema,
    validate_sync_config,
    validate_sync_perm_config_schema
)
from cowbird.monitoring.monitoring import Monitoring
from cowbird.utils import get_app_config, get_config_path, get_logger, print_log

LOGGER = get_logger(__name__)


def get_app(global_config=None, **settings):
    """
    This function returns the Pyramid WSGI application.

    It can also be used for test purpose (some config needed only in pyramid and not in tests are still in the main)
    """
    global_config = global_config or {}
    global_config.update(settings)
    config = get_app_config(global_config)

    services_cfgs = get_all_configs(get_config_path(), "services", allow_missing=True)
    service_names = set()
    for services_cfg in services_cfgs:
        service_names.update(services_cfg.keys())
        validate_services_config_schema(services_cfg)

    sync_perm_cfgs = get_all_configs(get_config_path(), "sync_permissions", allow_missing=True)
    # Validate sync_permissions config before starting the app
    for sync_perm_config in sync_perm_cfgs:
        validate_sync_perm_config_schema(sync_perm_config)
        for sync_cfg in sync_perm_config.values():
            validate_sync_config(sync_cfg, service_names)

    print_log("Starting Cowbird app...", LOGGER)
    wsgi_app = config.make_wsgi_app()

    # The main app is doing the monitoring
    if not sys.argv[0].endswith("celery"):
        # TODO: The monitoring should be done in a single worker to avoid picking an event multiple time
        Monitoring(config).start()

    return wsgi_app


def main(global_config=None, **settings):  # noqa: F811
    """
    This function returns the Pyramid WSGI application.
    """
    return get_app(global_config, **settings)


if __name__ == "__main__":
    main()
