import subprocess,sys,numpy as np
def frames(p,fps=8,w=96,h=170):
    r=subprocess.run(['ffmpeg','-v','error','-i',p,'-vf',f'fps={fps},scale={w}:{h},format=gray','-f','rawvideo','-'],capture_output=True)
    a=np.frombuffer(r.stdout,np.uint8).reshape(-1,h,w).astype(float); return a
for p in sys.argv[1:]:
    a=frames(p); d=np.abs(np.diff(a,axis=0)).mean(axis=(1,2))
    per=[round(d[i*8:(i+1)*8].mean(),1) for i in range(15)]
    print(p[-24:],'s1-5 avg',round(np.mean(per[:5]),1),'| per-sec',per)
