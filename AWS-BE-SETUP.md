## First run sync-to-ec2.sh locally in git-bash (ensure you have added the correct EC2 instance ID)



```bash

cd ShadowBot

./sync-to-ec2.sh

```



## AWS EC2 commands



1. Create python environment and install requirements



```bash

cd my-app

sudo apt install python3-venv

python3 -m venv env

```



```bash

source env/scripts/activate

python -m pip install -r requirements.txt

```



2. Playwright installation



```bash

sudo apt-get update

playwright install-deps

playwright install

```



3. ffmpeg installation



```bash

sudo apt-get install -y ffmpeg

ffmpeg -version

which ffmpeg   # should print /usr/bin/ffmpeg

```



4. Starting application



```bash

(env) ubuntu@ip-172-31-6-119:~/my-app$ python api\_server.py

```



