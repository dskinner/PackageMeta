"""
Copyright (c) 2012, Daniel Skinner <daniel@dasa.cc>
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.
2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""
import logging
import threading
import os

import sublime
import sublime_plugin

PackageControl = __import__("Package Control")


def logger(level):
    sh = logging.StreamHandler()
    sh.setLevel(logging.DEBUG)
    sh.setFormatter(logging.Formatter('%(levelname)s:%(name)s:%(message)s'))
    log = logging.getLogger("PackageMeta")
    log.setLevel(level)
    log.addHandler(sh)
    return log


log = logger(logging.DEBUG)


_requires = {}
_receivers = {}


class Receiver(object):
    """Base class for receiving broadcast data.

    Subclassing this will automatically instantiate and register the class for receiving
    broadcast data. For example, to receive data from a broadcast given the name "lint_java",
    the following is all that is needed:

    class LintJavaReceiver(packagemeta.Receiver):
        channel = "lint_java"

        def receive(self, data):
            pass  # handle data

    The type of data received is determined by the broadcaster. Multiple receivers can watch
    the same channel and all receivers will be notified.

    Attributes:
        channel: key used to register a subclass for receiving broadcast data by the same name.
    """
    channel = None

    def receive(self, data):
        pass


def _register_receivers():
    """Find all subclasses of Receiver and register them for receiving broadcast data"""
    subs = Receiver.__subclasses__()
    for sub in subs:
        if sub.channel is None:
            log.warn("Receiver %s failed to define `channel` member.", sub)
            continue
        _receivers[sub.channel] = _receivers.get(sub.channel, []) + [sub()]


# TODO could be better
sublime.set_timeout(_register_receivers, 3000)


def broadcast(channel, data):
    """Broadcast data on a given channel.
    """
    if not isinstance(channel, (str, unicode)):
        raise Exception("")

    log.info("received broadcast for %s with data: %s", channel, data)

    def _broadcast():
        for receiver in _receivers.get(channel, []):
            receiver.receive(data)

    threading.Thread(target=_broadcast).start()


class PackageMetaBroadcastCommand(sublime_plugin.ApplicationCommand):
    """
    """
    def run(self, channel, data):
        broadcast(channel, data)

    def is_visible(self):
        return False


def exists(*pkgs):
    for pkg in pkgs:
        if not os.path.exists(os.path.join(sublime.packages_path(), pkg)):
            return False
    return True


def requires(*pkgs):
    """Decor for registering external dependencies within a module.

    Use of this decor should be constrained to the module level if poossible.
    When used, this registers the original module to be associated with a
    package dependency for the associated function. If the package is not
    available, then the function is not run, and `None` will be returned. For
    example:

    @packagemeta.requires("ExternalPackage")
    def configure_externalpackage(settings):
        settings.set("externalpackage_setting", True)

    Since the package is associated with the module, a quick panel command
    is also available for installing all dependencies via PackageControl.
    See `packagemeta.InstallRequires` for more info.
    """
    def _decor(fn):
        global _requires
        s = _requires.get(fn.__module__, set())
        for pkg in pkgs:
            s.add(pkg)
        _requires[fn.__module__] = s

        def _require(*args, **kwargs):
            if exists(pkg):
                return fn(*args, **kwargs)
        return _require
    return _decor


class PackageMetaSetRequiresCommand(sublime_plugin.WindowCommand):
    """WindowCommand to allow external plugins to register dependencies.

    In cases where an external plugin doesn't want to import PackageMeta directly,
    dependencies can still be registered via this window command. For example:

    def set_requires():
        kwargs = {
            "module": set_requires.__module__,
            "pkgs": ["PackageA", "PackageB"]
        }
        sublime.active_window().run_command("package_meta_set_requires", kwargs)

    See `PackageMetaInstallRequiresCommand` for details on showing a quick panel
    to install dependencies.
    """
    def run(self, module=None, pkgs=[]):
        log.debug("received module %s", module)
        log.debug("received pkgs %s", pkgs)
        global _requires
        s = _requires.get(module, set())
        for pkg in pkgs:
            s.add(pkg)
        _requires[module] = s


class PackageMetaInstallRequiresCommand(sublime_plugin.WindowCommand):
    """Base class for quick panel to install required pkgs

    If a plugin uses `packagemeta.requires`, subclassing this
    WindowCommand will provide a quick panel to list and install
    missing packages. For example, in the plugin:

    class PluginInstallRequiresCommand(packagemeta.PackageMetaInstallRequiresCommand):
        def is_visible(self):
            return self.visible()

    And include the following in the plugin's sublime-commands file:

    {
        "caption": "Plugin: Install Dependencies",
        "command": "plugin_install_requires"
    }

    The command will only be visible if a plugin passed to `packagemeta.requires`
    is not installed.

    If instead you're interacting with packagemeta via `run_command`, you'll first
    need to declare required packages at an appropriate time for the type of plugin
    being developed. See `PackageMetaSetRequiresCommand` for details on registering
    dependencies.

    Once dependencies are registered, create a WindowCommand such as:

    class PluginInstallRequiresCommand(sublime_plugin.WindowCommand):
        def run(self):
            self.window.run_command("package_meta_install_requires", {"module": self.__module__})

    Note: In all cases, only packages not installed will be displayed.
    """

    def run(self, module=None):
        log.debug("InstallRequiresCommand.run received module %s", module)
        self.module = module
        if not self.get_pkgs():
            return

        self.options = self.get_missing_pkgs()
        if not self.options:
            return

        if len(self.options) > 1:
            self.options.insert(0, "All Packages")

        self.window.show_quick_panel(self.options, self.on_done)

    def on_done(self, picked):
        if picked == -1:
            return

        option = self.options[picked]

        if option == "All Packages":
            for name in self.options[1:]:
                self.install_pkg(name)
        else:
            self.install_pkg(option)

    def get_pkgs(self):
        global _requires
        return _requires.get(self.get_module(), [])

    def get_module(self):
        if not hasattr(self, "module") or self.module is None:
            return self.__module__
        return self.module

    def get_missing_pkgs(self):
        p = sublime.packages_path()
        log.debug("packages_path: %s", p)
        installed = os.listdir(p)
        return [pkg for pkg in self.get_pkgs() if pkg not in installed]

    def install_pkg(self, name):
        thread = PackageControl.PackageInstallerThread(PackageControl.PackageManager(), name, None)
        thread.start()
        PackageControl.ThreadProgress(thread, 'Installing package %s' % name,
            'Package %s successfully %s' % (name, "installed"))

    def visible(self):
        if not self.get_missing_pkgs():
            return False
        return True
