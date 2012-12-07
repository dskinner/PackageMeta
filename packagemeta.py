"""
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

	Simply subclassing this class will instantiate and register the class for receiving
	broadcast data. For example, to receive data from a broadcast given the name "lint_java",
	the following is all that is needed:

	class LintJavaReceiver(packagemeta.Receiver):
		name = "lint_java"

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

	def _broadcast():
		for receiver in _receivers.get(channel, []):
			receiver.receive(data)

	threading.Thread(target=_broadcast).start()


def exists(*pkgs):
	for pkg in pkgs:
		if not os.path.exists(os.path.join(sublime.packages_path(), pkg)):
			return False
	return True


def requires(*pkgs):
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


class InstallRequires(sublime_plugin.WindowCommand):
	"""Base class for quick panel to install required pkgs

	If a plugin uses `packagemeta.requires`, subclassing this
	WindowCommand will provide a quick panel to list and install
	missing packages. For example, in the plugin:

	class PluginInstallRequiresCommand(packagemeta.InstallRequires):
		pass

	And include the following in the plugin's sublime-commands file:

	{
		"caption": "Plugin: Install Dependencies",
		"command": "plugin_install_requires"
	}

	The command will only be visible if a plugin passed to `requires`
	is not installed.

	"""

	@property
	def pkgs(self):
		global _requires
		return _requires.get(self.__module__, [])

	def run(self):
		if not self.pkgs:
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

	def get_missing_pkgs(self):
		p = sublime.packages_path()
		log.debug("packages_path: %s", p)
		installed = os.listdir(p)
		return [pkg for pkg in self.pkgs if pkg not in installed]

	def install_pkg(self, name):
		thread = PackageControl.PackageInstallerThread(PackageControl.PackageManager(), name, None)
		thread.start()
		PackageControl.ThreadProgress(thread, 'Installing package %s' % name,
			'Package %s successfully %s' % (name, "installed"))

	def is_visible(self):
		if not self.get_missing_pkgs():
			return False
		return True
