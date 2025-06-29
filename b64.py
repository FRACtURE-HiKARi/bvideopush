from base64 import encodebytes, decodebytes
import sys

if (len(sys.argv)) != 3:
    print('bad usage.')
    exit()

if sys.argv[1] == '-e':
    print(encodebytes(sys.argv[2].encode()).decode())
elif sys.argv[1] == '-d':
    print(decodebytes(sys.argv[2].encode()).decode())
else:
    print("bad usage.")
