[app]
title = سامانه آماد و پشتیبانی
package.name = amad_support
package.domain = ir.sayyad.amad
source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,atlas,ttf,mp3,wav,m4a,json,md
version = 5.0.0
requirements = python3,kivy==2.3.0,arabic-reshaper,python-bidi
orientation = portrait
fullscreen = 0
android.permissions = INTERNET,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE
android.api = 35
android.minapi = 24
android.archs = arm64-v8a
android.accept_sdk_license = True
p4a.branch = develop

[buildozer]
log_level = 2
warn_on_root = 1
