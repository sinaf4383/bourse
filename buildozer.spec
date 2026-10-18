[app]
title = Bourse
package.name = bourse
package.domain = org.bourse
source.dir = .
source.include_exts = py
version = 0.1
requirements = python3,requests,urllib3,idna,charset-normalizer,certifi
orientation = portrait
fullscreen = 0
android.permissions = INTERNET
android.api = 33
android.minapi = 24
android.ndk = 25b
android.archs = arm64-v8a
android.accept_sdk_license = True
p4a.branch = v2024.01.21
p4a.bootstrap = webview
p4a.port = 5000

[buildozer]
log_level = 2
warn_on_root = 1
