const RUNTIME_ENVIRONMENT_KEYS = [
  "PATH",
  "HOME",
  "USERPROFILE",
  "APPDATA",
  "LOCALAPPDATA",
  "ProgramData",
  "SystemRoot",
  "WINDIR",
  "COMSPEC",
  "TEMP",
  "TMP",
  "TMPDIR",
  "LANG",
  "LC_ALL",
  "LC_CTYPE",
  "TZ",
  "XDG_CONFIG_HOME",
  "XDG_CACHE_HOME",
  "XDG_DATA_HOME",
  "XDG_STATE_HOME",
  "XDG_RUNTIME_DIR",
  "SSL_CERT_FILE",
  "SSL_CERT_DIR",
];

function createNeosisEnvironment(environment, home, { electronRunAsNode = false } = {}) {
  const selected = {};
  for (const name of RUNTIME_ENVIRONMENT_KEYS) {
    if (typeof environment[name] === "string") selected[name] = environment[name];
  }
  selected.NEOSIS_HOME = home;
  if (electronRunAsNode) selected.ELECTRON_RUN_AS_NODE = "1";
  return selected;
}

module.exports = { createNeosisEnvironment };
