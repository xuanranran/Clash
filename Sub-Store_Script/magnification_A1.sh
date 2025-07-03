// Script Operator
// 更新版本：该脚本在原位置标准化倍率，而不是移动到末尾。
// 例如：将 "A丨1x B" 转换为 "A丨[x1] B"

function operator(proxies, targetPlatform, context) {
  // proxies 是一个包含所有节点信息的数组
  return proxies.map(proxy => {
    let name = proxy.name;

    // 核心修改：不再将标签移动到末尾，而是在找到的位置直接替换。
    // 这样可以保留原始名称的结构。

    // 规则 1: 处理 [倍率:1] 这样的格式
    name = name.replace(/\[倍率:(\d+\.?\d*)\]/g, '[x$1]');

    // 规则 2: 处理 "1x", "1 x", "1.5倍率" 这样的格式 (数字在前)
    name = name.replace(/(\d+\.?\d*)\s?(x|X|倍率)/g, '[x$1]');

    // 规则 3: 处理 "x1", "X 1" 这样的格式 (x/X在前)
    name = name.replace(/(x|X)\s?(\d+\.?\d*)/g, '[x$2]');

    // 清理工作: 清理可能产生的多余空格
    name = name.replace(/\s+/g, ' ').trim();

    // 将修改后的名称写回节点
    proxy.name = name;
    
    // 必须返回修改后的 proxy 对象
    return proxy;
  });
}