const { createProxyMiddleware } = require('http-proxy-middleware');

module.exports = function (app) {
  // Forward API and uploaded assets to the Express backend.
  app.use(
    ['/api', '/uploads'],
    createProxyMiddleware({
      target: 'http://127.0.0.1:5000',
      changeOrigin: true,
    })
  );
};
