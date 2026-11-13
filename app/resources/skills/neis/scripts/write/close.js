const { D } = require('./lib2.js');
module.exports = async (page) => { await D.press(page, '닫기'); return await D.read(page); };
