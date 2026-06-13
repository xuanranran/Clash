// Script Operator
// 将各种倍率写法原位统一为 [x数字]，并清理重复方括号。

function operator(proxies, targetPlatform, context) {
  const number = String.raw`\d+(?:\.\d+)?`;
  const multiplierPattern = new RegExp(
    String.raw`\[+\s*(?:(?:x|X|倍率\s*:)\s*${number}|${number}\s*(?:x|X|倍率))\s*\]+` +
      String.raw`|(?:(?:x|X|倍率\s*:)\s*${number}|${number}\s*(?:x|X|倍率))`,
    'g'
  );

  return proxies.map(proxy => {
    let name = proxy.name;

    name = name.replace(multiplierPattern, match => {
      const numberPart = match.match(new RegExp(number))[0];
      return `[x${numberPart}]`;
    });

    proxy.name = name.replace(/\s+/g, ' ').trim();
    return proxy;
  });
}
