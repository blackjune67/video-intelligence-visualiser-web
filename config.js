const CONFIG = {
    GCP_SERVER_IP: '34.64.43.132',
    GCP_SERVER_PORT: 443,
    LOCAL_HOST_PORT: 8080
};

// CommonJS module syntax
if (typeof module !== 'undefined' && module.exports) {
    module.exports = CONFIG;
}
// ES6 module syntax
else if (typeof exports !== 'undefined') {
    exports.default = CONFIG;
}
// Browser global
else {
    window.CONFIG = CONFIG;
}