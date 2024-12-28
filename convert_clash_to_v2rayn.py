import yaml

def clash_to_v2rayn(clash_config_str):
    """
    将 Clash for Windows 样式的配置文本转换成
    类似“V2RayN 多 socks 端口 + Trojan 代理”风格的配置。
    :param clash_config_str: str, Clash 配置的 YAML 文本
    :return: str, 转换后 YAML 文本
    """

    data = yaml.safe_load(clash_config_str)

    # 1) 读取 Clash 中的 proxies 列表
    if 'proxies' not in data:
        raise ValueError("此配置无 'proxies' 字段，无法转换。")

    proxies = data['proxies']
    # proxies 通常是一个 list，每个 item 形如：
    # { name: '🇭🇰 香港 IEPL [01] [Air]', type: trojan, server: ..., port: ..., password: ... }

    # 2) 准备 v2rayn 所需的部分字段
    #    - allow-lan, dns, listeners, proxies, ...
    #    这里我们先按照你提供的“上面格式”进行组装

    result = {
        'allow-lan': True,
        'dns': {
            'enable': True,
            'enhanced-mode': 'fake-ip',
            'fake-ip-range': '198.18.0.1/16',
            'default-nameserver': ['114.114.114.114'],
            'nameserver': ['https://doh.pub/dns-query']
        },
        'listeners': [],
        'proxies': []
    }

    # 注意：在你提供的“上面配置”中，所有 proxies 都放在 result['proxies'] ，
    # 每个 Trojan 代理都要映射为：
    #   - name: ...
    #     type: trojan
    #     server: ...
    #     port: ...
    #     password: ...
    #     ...

    # 同时，还要给每个 Trojan 代理对应一个 “listeners” 端口，比如 50000, 50001, ...
    # 这些端口数值可以按顺序递增

    base_port = 50000
    for i, p in enumerate(proxies):
        # Clash Trojan => V2RayN Trojan
        # 把 name, server, port, password 都取出来
        name = p.get('name', f'proxy{i}')
        server = p.get('server', '1.1.1.1')
        trojan_port = p.get('port', 443)
        password = p.get('password', 'pass123')
        # 也可能有 skip-cert-verify, udp, alpn, etc...

        # “listeners” 每个 item:
        #   - name: mixed0
        #     type: mixed
        #     port: 50000
        #     proxy: 🇭🇰 香港 IEPL...
        listener_item = {
            'name': f'mixed{i}',
            'type': 'mixed',
            'port': base_port + i,
            'proxy': name
        }
        result['listeners'].append(listener_item)

        # “proxies” 每个 item:
        #   - name: ...
        #     type: trojan
        #     server: ...
        #     port: ...
        #     password: ...
        #     udp: true
        #     ...
        proxy_item = {
            'name': name,
            'type': 'trojan',
            'server': server,
            'port': trojan_port,
            'password': password,
            'udp': True,            # Clash 中若 udp:true 就也复制
            'alpn': p.get('alpn', ['h2', 'http/1.1']),
            'skip-cert-verify': p.get('skip-cert-verify', True),
        }
        result['proxies'].append(proxy_item)

    # 3) 组合其他字段
    # 你在“上面配置”里有 70+ 个 listener，这里我们只要按实际 proxies 数量自动生成即可
    # 其余没有需要可不写，或者你也可以手动写死多余

    # 4) 转成 YAML
    output_yaml = yaml.dump(result, sort_keys=False, allow_unicode=True)
    return output_yaml


if __name__ == '__main__':
    # 假设把 Clash for Windows 配置保存到 "clash_config.yaml"
    with open('clash_config.yaml', 'r', encoding='utf-8') as f:
        clash_config_str = f.read()

    v2rayn_yaml = clash_to_v2rayn(clash_config_str)
    # 将转换结果写到 "converted_v2rayn.yaml"
    with open('converted_v2rayn.yaml', 'w', encoding='utf-8') as f:
        f.write(v2rayn_yaml)

    print("转换完成，输出到 converted_v2rayn.yaml")
