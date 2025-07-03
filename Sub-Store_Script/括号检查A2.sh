// Script Operator
// 最终修正版：解决双括号问题，并正确处理各种倍率格式。

function operator(proxies, targetPlatform, context) {
  return proxies.map(proxy => {
    let name = proxy.name;

    // 步骤 1: 寻找并提取倍率的核心数字
    // 使用一个正则表达式来匹配所有可能的倍率格式
    // 无论是 [x1], [[x1]], 1x, x1, [倍率:1] 等，都只提取出数字 "1"
    const regex = /\[*\s*(?:x|X|倍率:)\s*(\d+\.?\d*)\s*\]*/;
    const match = name.match(regex);

    // 如果找到了匹配的倍率
    if (match) {
      // match[0] 是匹配到的完整文本，例如 "[[x1]]" 或 "1x"
      const fullMatchText = match[0]; 
      // match[1] 是我们需要的核心数字，例如 "1"
      const numberPart = match[1];

      // 步骤 2: 进行替换
      // 将原始的、不规范的倍率文本 (fullMatchText) 替换为标准格式
      const standardTag = `[x${numberPart}]`;
      name = name.replace(fullMatchText, standardTag);
    }
    
    // 步骤 3: 清理工作
    // 清理可能产生的多余空格，确保格式优美
    name = name.replace(/\s+/g, ' ').trim();

    // 将修改后的名称写回节点
    proxy.name = name;
    
    return proxy;
  });
}