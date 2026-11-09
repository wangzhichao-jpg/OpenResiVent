"""仅监听回环地址的桌面启动器。"""

import socket
import threading
import time
import webbrowser

import uvicorn


def desktop():
    """绑定随机本机端口、启动服务，并优先打开内嵌窗口。"""
    # 保持 socket 打开并交给 uvicorn，避免预选端口后被抢占。
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    port = sock.getsockname()[1]
    config = uvicorn.Config(
        "openresivent.api:app", host="127.0.0.1", port=port, log_level="warning"
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(
        target=lambda: server.run(sockets=[sock]), name="openresivent-server", daemon=True
    )
    thread.start()
    try:
        deadline = time.monotonic() + 15
        while not server.started:
            if not thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError("本机服务启动失败")
            time.sleep(0.05)
        url = f"http://127.0.0.1:{port}/"
        try:
            import webview
        except ImportError:
            print(f"未安装桌面窗口组件，将打开默认浏览器：{url}", flush=True)
            webbrowser.open(url)
            while thread.is_alive():
                thread.join(0.5)
        else:
            webview.create_window("住宅通风设计", url)
            webview.start()
    except KeyboardInterrupt:
        pass
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
