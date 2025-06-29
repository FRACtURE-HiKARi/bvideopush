## 脚本获取木柜子二创（自用）

### 使用方法
1. 安装依赖 `pip install aiohttp qrcode`
2. 登录，运行`python -m login.main`,  然后在浏览器里打开[http://localhost:8080](http://localhost:8080)，获取二维码用b站app扫码登录
3. 登录成功后（cookies文件夹里出现了一个有SESSID的json）运行 `python -m poll.poll_videos`，结果将被保存在results.txt里面。

参考文档：[BAC Document](https://socialsisteryi.github.io/bilibili-API-collect)
