// 보이는 대화상자(cleo dialog) 글과 버튼
module.exports.read = async (page) => page.evaluate(() => {
  const ds = [...document.querySelectorAll('.cl-dialog, [role=dialog], [role=alertdialog]')].filter(d => d.offsetParent);
  return ds.map(d => ({ text: d.innerText.replace(/\s+/g, ' ').trim().slice(0, 400), buttons: [...d.querySelectorAll('.cl-button, button')].filter(b => b.offsetParent).map(b => b.innerText.trim()) }));
});
module.exports.press = async (page, label) => {
  const b = page.locator('.cl-dialog:visible, [role=dialog]:visible, [role=alertdialog]:visible').locator('.cl-button:visible, button:visible').filter({ hasText: new RegExp('^\s*' + label + '\s*$') }).last();
  await b.click({ timeout: 8000 }); await page.waitForTimeout(1500);
};
