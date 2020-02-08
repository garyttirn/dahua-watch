# dahua-watch

Script to monitor Amcrest/Dahua Camera Events and report those events to Motion Sensor on Vera Controllers (https://getvera.com/collections/controllers-products) 
Works with https://github.com/garyttirn/vera-amcrest

Based on https://github.com/johnnyletrois/dahua-watch 

## Installation ##

Download watch.py to /usr/local/sbin/watch.py

Make sure you have python3 and pycurl-library

On Ubuntu 18.04 :
`apt install python3 python3-pycurl`

### set permissions ###
`chmod 755 /usr/local/sbin/watch.py`

## systemd integration ##

Download watch.service to /etc/systemd/system/watch.service

`systemctl daemon-reload`

`systemctl enable --now watch`

`systemctl status watch`

