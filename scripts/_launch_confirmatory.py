import subprocess, sys, os
os.chdir(r'C:\dev\_w')
log = open(r'C:\Users\Zain\AppData\Local\Temp\confirmatory3.log', 'a', buffering=1, encoding='utf-8')
subprocess.run([sys.executable.replace('pythonw','python'), '-u',
                r'scripts\run_confirmatory.py'], stdout=log, stderr=log)
