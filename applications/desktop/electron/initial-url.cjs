function loginUrlForOrigin(origin) {
  return new URL("/auth/login", origin).toString();
}

module.exports = { loginUrlForOrigin };
