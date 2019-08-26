"""
PREDSTORM real time solar wind forecasting from L1 solar wind data

predicting the L1 solar wind and Dst index with analogue ensembles
for similar algorithms see Riley et al. 2017, Owens et al. 2017

Author: C. Moestl, IWF Graz, Austria
twitter @chrisoutofspace, https://github.com/IWF-helio

started April 2018, last update August 2019

python 3.7 with sunpy

method
semi-supervised learning: add known intervals of ICMEs, MFRs and CIRs in the training data
helcats lists for ICMEs at Wind since 2007
HSS e.g. https://link.springer.com/article/10.1007%2Fs11207-013-0355-z
https://en.wikipedia.org/wiki/Pattern_recognition


Things to do:
use recarrays!

DSCOVR data:
Nans for missing data should be handled better and interpolated over, OBrien stops with Nans

training data:
use stereo one hour data as training data set, corrected for 1 AU
use VEX and MESSENGER as tests for HelioRing like forecasts, use STEREO at L5 for training data of the last few days

forecast plot:
add approximate levels of Dst for each location to see aurora, taken from ovation prime/worldview and Dst
add Temerin and Li method and kick out Burton/OBrien; make error bars for Dst
take mean of ensemble forecast for final blue line forecast or only best match?



MIT LICENSE
Copyright 2018, Christian Moestl
Permission is hereby granted, free of charge, to any person obtaining a copy of this
software and associated documentation files (the "Software"), to deal in the Software
without restriction, including without limitation the rights to use, copy, modify,
merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so, subject to the following
conditions:
The above copyright notice and this permission notice shall be included in all copies
or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF
CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE
OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

"""

##########################################################################################
####################################### CODE START #######################################
##########################################################################################

################################## INPUT PARAMETERS ######################################
import os
import sys
import getopt

# READ INPUT OPTIONS FROM COMMAND LINE
argv = sys.argv[1:]
opts, args = getopt.getopt(argv,"h",["server", "help"])

server = False
if "--server" in [o for o, v in opts]:
    server = True
    print("In server mode!")

import matplotlib
if server:
    matplotlib.use('Agg') # important for server version, otherwise error when making figures
else:
    matplotlib.use('Qt5Agg') # figures are shown on mac

from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from matplotlib.dates import num2date, date2num, DateFormatter
import numpy as np
import time
import pickle
import copy
import pdb
import urllib
import json
import seaborn as sns
import scipy
from scipy import stats
import sunpy.time

import predstorm as ps
from predstorm_l1_input import *

#========================================================================================
#--------------------------------- FUNCTIONS --------------------------------------------
#========================================================================================

def get_dscovr_data_real_old():
    """
    Downloads and returns DSCOVR data 
    data from http://services.swpc.noaa.gov/products/solar-wind/
    if needed replace with ACE
    http://legacy-www.swpc.noaa.gov/ftpdir/lists/ace/
    get 3 or 7 day data
    url_plasma='http://services.swpc.noaa.gov/products/solar-wind/plasma-3-day.json'
    url_mag='http://services.swpc.noaa.gov/products/solar-wind/mag-3-day.json'
    
    Parameters
    ==========
    None
    Returns
    =======
    (data_minutes, data_hourly)
    data_minutes : np.rec.array
         Array of interpolated minute data with format:
         dtype=[('time','f8'),('btot','f8'),('bxgsm','f8'),('bygsm','f8'),('bzgsm','f8'),\
            ('speed','f8'),('den','f8'),('temp','f8')]
    data_hourly : np.rec.array
         Array of interpolated hourly data with format:
         dtype=[('time','f8'),('btot','f8'),('bxgsm','f8'),('bygsm','f8'),('bzgsm','f8'),\
            ('speed','f8'),('den','f8'),('temp','f8')]
    """
    
    url_plasma='http://services.swpc.noaa.gov/products/solar-wind/plasma-7-day.json'
    url_mag='http://services.swpc.noaa.gov/products/solar-wind/mag-7-day.json'

    #download, see URLLIB https://docs.python.org/3/howto/urllib2.html
    with urllib.request.urlopen(url_plasma) as url:
        pr = json.loads (url.read().decode())
    with urllib.request.urlopen(url_mag) as url:
        mr = json.loads(url.read().decode())
    logger.info('get_dscovr_data_real: DSCOVR plasma data available')
    logger.info(str(pr[0]))
    logger.info('get_dscovr_data_real: DSCOVR MAG data available')
    logger.info(str(mr[0]))
    #kill first row which stems from the description part
    pr=pr[1:]
    mr=mr[1:]

    #define variables 
    #plasma
    rptime_str=['']*len(pr)
    rptime_num=np.zeros(len(pr))
    rpv=np.zeros(len(pr))
    rpn=np.zeros(len(pr))
    rpt=np.zeros(len(pr))

    #mag
    rbtime_str=['']*len(mr)
    rbtime_num=np.zeros(len(mr))
    rbtot=np.zeros(len(mr))
    rbzgsm=np.zeros(len(mr))
    rbygsm=np.zeros(len(mr))
    rbxgsm=np.zeros(len(mr))

    #convert variables to numpy arrays
    #mag
    for k in np.arange(0,len(mr),1):

        #handle missing data, they show up as None from the JSON data file
        if mr[k][6] is None: mr[k][6]=np.nan
        if mr[k][3] is None: mr[k][3]=np.nan
        if mr[k][2] is None: mr[k][2]=np.nan
        if mr[k][1] is None: mr[k][1]=np.nan

        rbtot[k]=float(mr[k][6])
        rbzgsm[k]=float(mr[k][3])
        rbygsm[k]=float(mr[k][2])
        rbxgsm[k]=float(mr[k][1])

        #convert time from string to datenumber
        rbtime_str[k]=mr[k][0][0:16]
        rbtime_num[k]=date2num(datetime.strptime(rbtime_str[k], "%Y-%m-%d %H:%M"))
    
    #plasma
    for k in np.arange(0,len(pr),1):
        if pr[k][2] is None: pr[k][2]=np.nan
        rpv[k]=float(pr[k][2]) #speed
        rptime_str[k]=pr[k][0][0:16]
        rptime_num[k]=date2num(datetime.strptime(rbtime_str[k], "%Y-%m-%d %H:%M"))
        if pr[k][1] is None: pr[k][1]=np.nan
        rpn[k]=float(pr[k][1]) #density
        if pr[k][3] is None: pr[k][3]=np.nan
        rpt[k]=float(pr[k][3]) #temperature


    #interpolate to minutes 
    #rtimes_m=np.arange(rbtime_num[0],rbtime_num[-1],1.0000/(24*60))
    rtimes_m= round_to_hour(num2date(rbtime_num[0])) + np.arange(0,len(rbtime_num)) * timedelta(minutes=1) 
    #convert back to matplotlib time
    rtimes_m=date2num(rtimes_m)

    rbtot_m=np.interp(rtimes_m,rbtime_num,rbtot)
    rbzgsm_m=np.interp(rtimes_m,rbtime_num,rbzgsm)
    rbygsm_m=np.interp(rtimes_m,rbtime_num,rbygsm)
    rbxgsm_m=np.interp(rtimes_m,rbtime_num,rbxgsm)
    rpv_m=np.interp(rtimes_m,rptime_num,rpv)
    rpn_m=np.interp(rtimes_m,rptime_num,rpn)
    rpt_m=np.interp(rtimes_m,rptime_num,rpt)
    
    #interpolate to hours 
    #rtimes_h=np.arange(np.ceil(rbtime_num)[0],rbtime_num[-1],1.0000/24.0000)
    rtimes_h= round_to_hour(num2date(rbtime_num[0])) + np.arange(0,len(rbtime_num)/(60)) * timedelta(hours=1) 
    rtimes_h=date2num(rtimes_h)

    
    rbtot_h=np.interp(rtimes_h,rbtime_num,rbtot)
    rbzgsm_h=np.interp(rtimes_h,rbtime_num,rbzgsm)
    rbygsm_h=np.interp(rtimes_h,rbtime_num,rbygsm)
    rbxgsm_h=np.interp(rtimes_h,rbtime_num,rbxgsm)
    rpv_h=np.interp(rtimes_h,rptime_num,rpv)
    rpn_h=np.interp(rtimes_h,rptime_num,rpn)
    rpt_h=np.interp(rtimes_h,rptime_num,rpt)

    #make recarrays
    data_hourly=np.rec.array([rtimes_h,rbtot_h,rbxgsm_h,rbygsm_h,rbzgsm_h,rpv_h,rpn_h,rpt_h], \
    dtype=[('time','f8'),('btot','f8'),('bxgsm','f8'),('bygsm','f8'),('bzgsm','f8'),\
            ('speed','f8'),('den','f8'),('temp','f8')])
    
    data_minutes=np.rec.array([rtimes_m,rbtot_m,rbxgsm_m,rbygsm_m,rbzgsm_m,rpv_m,rpn_m,rpt_m], \
    dtype=[('time','f8'),('btot','f8'),('bxgsm','f8'),('bygsm','f8'),('bzgsm','f8'),\
            ('speed','f8'),('den','f8'),('temp','f8')])
        
    return data_minutes, data_hourly


def get_omni_data_old():
    """FORMAT(2I4,I3,I5,2I3,2I4,14F6.1,F9.0,F6.1,F6.0,2F6.1,F6.3,F6.2, F9.0,F6.1,F6.0,2F6.1,F6.3,2F7.2,F6.1,I3,I4,I6,I5,F10.2,5F9.2,I3,I4,2F6.1,2I6,F5.1)
    1963   1  0 1771 99 99 999 999 999.9 999.9 999.9 999.9 999.9 999.9 999.9 999.9 999.9 999.9 999.9 999.9 999.9 999.9 9999999. 999.9 9999. 999.9 999.9 9.999 99.99 9999999. 999.9 9999. 999.9 999.9 9.999 999.99 999.99 999.9  7  23    -6  119 999999.99 99999.99 99999.99 99999.99 99999.99 99999.99  0   3 999.9 999.9 99999 99999 99.9
    define variables from OMNI2 dataset
    see http://omniweb.gsfc.nasa.gov/html/ow_data.html
    omni2_url='ftp://nssdcftp.gsfc.nasa.gov/pub/data/omni/low_res_omni/omni2_all_years.dat'
    """

    #check how many rows exist in this file
    f=open('data/omni2_all_years.dat')
    dataset= len(f.readlines())
    #print(dataset)
    #global Variables
    spot=np.zeros(dataset) 
    btot=np.zeros(dataset) #floating points
    bx=np.zeros(dataset) #floating points
    by=np.zeros(dataset) #floating points
    bz=np.zeros(dataset) #floating points
    bzgsm=np.zeros(dataset) #floating points
    bygsm=np.zeros(dataset) #floating points

    speed=np.zeros(dataset) #floating points
    speedx=np.zeros(dataset) #floating points
    speed_phi=np.zeros(dataset) #floating points
    speed_theta=np.zeros(dataset) #floating points

    dst=np.zeros(dataset) #float
    kp=np.zeros(dataset) #float

    den=np.zeros(dataset) #float
    pdyn=np.zeros(dataset) #float
    year=np.zeros(dataset)
    day=np.zeros(dataset)
    hour=np.zeros(dataset)
    t=np.zeros(dataset) #index time
    
    
    j=0
    print('Read OMNI2 data ...')
    with open('data/omni2_all_years.dat') as f:
        for line in f:
            line = line.split() # to deal with blank 
            #print line #41 is Dst index, in nT
            dst[j]=line[40]
            kp[j]=line[38]
            
            if dst[j] == 99999: dst[j]=np.NaN
            #40 is sunspot number
            spot[j]=line[39]
            #if spot[j] == 999: spot[j]=NaN

            #25 is bulkspeed F6.0, in km/s
            speed[j]=line[24]
            if speed[j] == 9999: speed[j]=np.NaN
          
            #get speed angles F6.1
            speed_phi[j]=line[25]
            if speed_phi[j] == 999.9: speed_phi[j]=np.NaN

            speed_theta[j]=line[26]
            if speed_theta[j] == 999.9: speed_theta[j]=np.NaN
            #convert speed to GSE x see OMNI website footnote
            speedx[j] = - speed[j] * np.cos(np.radians(speed_theta[j])) * np.cos(np.radians(speed_phi[j]))



            #9 is total B  F6.1 also fill ist 999.9, in nT
            btot[j]=line[9]
            if btot[j] == 999.9: btot[j]=np.NaN

            #GSE components from 13 to 15, so 12 to 14 index, in nT
            bx[j]=line[12]
            if bx[j] == 999.9: bx[j]=np.NaN
            by[j]=line[13]
            if by[j] == 999.9: by[j]=np.NaN
            bz[j]=line[14]
            if bz[j] == 999.9: bz[j]=np.NaN
          
            #GSM
            bygsm[j]=line[15]
            if bygsm[j] == 999.9: bygsm[j]=np.NaN
          
            bzgsm[j]=line[16]
            if bzgsm[j] == 999.9: bzgsm[j]=np.NaN    
          
          
            #24 in file, index 23 proton density /ccm
            den[j]=line[23]
            if den[j] == 999.9: den[j]=np.NaN
          
            #29 in file, index 28 Pdyn, F6.2, fill values sind 99.99, in nPa
            pdyn[j]=line[28]
            if pdyn[j] == 99.99: pdyn[j]=np.NaN      
          
            year[j]=line[0]
            day[j]=line[1]
            hour[j]=line[2]
            j=j+1     
      

    #convert time to matplotlib format
    #http://matplotlib.org/examples/pylab_examples/date_demo2.html

    times1=np.zeros(len(year)) #datetime time
    print('convert time start')
    for index in range(0,len(year)):
        #first to datetimeobject 
        timedum=datetime(int(year[index]), 1, 1) + timedelta(day[index] - 1) +timedelta(hours=hour[index])
        #then to matlibplot dateformat:
        times1[index] = date2num(timedum)
    print('convert time done')   #for time conversion

    print('all done.')
    print(j, ' datapoints')   #for reading data from OMNI file
    
    #make structured array of data
    omni_data=np.rec.array([times1,btot,bx,by,bz,bygsm,bzgsm,speed,speedx,den,pdyn,dst,kp], \
    dtype=[('time','f8'),('btot','f8'),('bx','f8'),('by','f8'),('bz','f8'),\
    ('bygsm','f8'),('bzgsm','f8'),('speed','f8'),('speedx','f8'),('den','f8'),('pdyn','f8'),('dst','f8'),('kp','f8')])
    
    return omni_data


def round_to_hour(dt):
    '''
    round datetime objects to nearest hour
    '''
    dt_start_of_hour = dt.replace(minute=0, second=0, microsecond=0)
    dt_half_hour = dt.replace(minute=30, second=0, microsecond=0)

    if dt >= dt_half_hour:
        # round up
        dt = dt_start_of_hour + timedelta(hours=1)
    else:
        # round down
        dt = dt_start_of_hour
    return dt

#========================================================================================
#--------------------------------- MAIN PROGRAM -----------------------------------------
#========================================================================================


plt.close('all')

print()
print()

print('------------------------------------------------------------------------')
print()
print('PREDSTORM L1 v1 method for geomagnetic storm and aurora forecasting. ')
print('Christian Moestl, IWF Graz, last update August 2019.')
print()
print('Based on results by Riley et al. 2017 Space Weather, and')
print('Owens, Riley and Horbury 2017 Solar Physics. ')
print()
print('This is a pattern recognition technique that searches ')
print('for similar intervals in historic data as the current solar wind - also known as Analogue Ensembles (AnEn).')
print()
print('This is the real time version by Christian Moestl, IWF Graz, Austria. Last update: April 2019. ')
print()
print('------------------------------------------------------------------------')

logger = ps.init_logging()

if os.path.isdir('real') == False: 
    os.mkdir('real')
if os.path.isdir('data') == False:
    os.mkdir('data')

#================================== (1) GET DATA ========================================

######################### (1a) get real time DSCOVR data ##################################

logger.info("Loading real-time DSCOVR data...")
dscovr = ps.get_dscovr_realtime_data()

# get time of the last entry in the DSCOVR data
timenow = dscovr['time'][-1]
timenowstr = num2date(timenow).strftime("%Y-%m-%d %H:%M")

# get UTC time now
timestamp = datetime.utcnow()
timeutc = date2num(timestamp)
timeutcstr = timestamp.strftime("%Y-%m-%d %H:%M")

print()
print()
print('Current time UTC')
print(timeutcstr)
print('UTC Time of last datapoint in real time DSCOVR data')
print(timenowstr)
print('Time lag in minutes:', int(round((timeutc-timenow)*24*60)))
print()

logger.info('Load real time Dst from Kyoto via NOAA')
dst = ps.get_noaa_dst()

logger.info("Loading OMNI2 dataset...")
if not os.path.exists('data/omni2_all_years.dat'):
    omni = ps.get_omni_data(download=True)
    pickle.dump(omni, open('data/omni2_all_years_pickle.p', 'wb') )
    #see http://omniweb.gsfc.nasa.gov/html/ow_data.html
    # print('download OMNI2 data from')
    # omni2_url='ftp://nssdcftp.gsfc.nasa.gov/pub/data/omni/low_res_omni/omni2_all_years.dat'
    # print(omni2_url)
    # try: urllib.request.urlretrieve(omni2_url, 'data/omni2_all_years.dat')
    # except urllib.error.URLError as e:
    #     print(' ', omni2_url,' ',e.reason)
else:
    #if omni2 hourly data is not yet converted and saved as pickle, do it:
    if not os.path.exists('data/omni2_all_years_pickle.p'):
        #load OMNI2 dataset from .dat file with a function from dst_module.py
        omni = ps.get_omni_data()
        #contains: omni time,day,hour,btot,bx,by,bz,bygsm,bzgsm,speed,speedx,den,pdyn,dst,kp
        #save for faster loading later
        pickle.dump(omni, open('data/omni2_all_years_pickle.p', 'wb') )
    else:  
        omni = pickle.load(open('data/omni2_all_years_pickle.p', 'rb') )

#interpolate to 1 hour steps: make an array from last time in hour steps backwards for 24 hours, then interpolate


#this is the last 24 hours in 1 hour timesteps, 25 data points
#for field
rbtimes24=np.arange(dscovr['time'][-1]-1,dscovr['time'][-1]+1/24,1/24)
btot24=np.interp(rbtimes24,dscovr['time'],dscovr['btot'])
bzgsm24=np.interp(rbtimes24,dscovr['time'],dscovr['bz'])
bygsm24=np.interp(rbtimes24,dscovr['time'],dscovr['by'])
bxgsm24=np.interp(rbtimes24,dscovr['time'],dscovr['bx'])

#for plasma
rptimes24=np.arange(dscovr['time'][-1]-1,dscovr['time'][-1]+1/24,1/24)
rpv24=np.interp(rptimes24,dscovr['time'],dscovr['speed'])
rpn24=np.interp(rptimes24,dscovr['time'],dscovr['density'])

#define times of the future wind, deltat hours after current time
timesfp=np.arange(rptimes24[-1],rptimes24[-1]+1+1/24,1/24)
timesfb=np.arange(rbtimes24[-1],rbtimes24[-1]+1+1/24,1/24)


###calculate Dst for DSCOVR last 7 day data with Burton and OBrien
#this is the last 24 hours in 1 hour timesteps, 25 data points
#start on next day 0 UT, so rbtimes7 contains values at every full hour like the real Dst
rtimes7=np.arange(np.ceil(dscovr['time'])[0],dscovr['time'][-1],1.0000/24)
btot7=np.interp(rtimes7,dscovr['time'],dscovr['btot'])
bzgsm7=np.interp(rtimes7,dscovr['time'],dscovr['bz'])
bygsm7=np.interp(rtimes7,dscovr['time'],dscovr['by'])
bxgsm7=np.interp(rtimes7,dscovr['time'],dscovr['bx'])
rpv7=np.interp(rtimes7,dscovr['time'],dscovr['speed'])
rpn7=np.interp(rtimes7,dscovr['time'],dscovr['density'])

#interpolate NaN values in the hourly interpolated data ******* to add


print('Loaded Kyoto Dst from NOAA for last 7 days.')

#make Dst index from solar wind data
#make_dst_from_wind(btot_in,bx_in, by_in,bz_in,v_in,vx_in,density_in,time_in):#
rdst_temerin_li=ps.predict.calc_dst_temerin_li(rtimes7,btot7,bxgsm7,bygsm7,bzgsm7,rpv7,rpv7,rpn7)
rdst_obrien = ps.predict.calc_dst_obrien(rtimes7, bzgsm7, rpv7, rpn7)
rdst_burton = ps.predict.calc_dst_burton(rtimes7, bzgsm7, rpv7, rpn7)



##################### plot DSCOVR data
sns.set_context("talk")
sns.set_style("darkgrid")
fig=plt.figure(1,figsize=(12,10)) #fig=plt.figure(1,figsize=(14,14))
weite=1
fsize=11
msize=5

#panel 1
ax4 = fig.add_subplot(411)
plt.plot_date(dscovr['time'], dscovr['btot'],'-k', label='B total', linewidth=weite)
if showinterpolated: plt.plot_date(rbtimes24, btot24,'ro', label='B total interpolated last 24 hours',linewidth=weite,markersize=msize)
plt.plot_date(dscovr['time'], dscovr['bz'],'-g', label='Bz GSM',linewidth=weite)
if showinterpolated: plt.plot_date(rbtimes24, bzgsm24,'go', label='Bz GSM interpolated last 24 hours',linewidth=weite,markersize=msize)


#indicate 0 level for Bz
plt.plot_date([rtimes7[0], rtimes7[-1]], [0,0],'--k', alpha=0.5, linewidth=1)


#test interpolation
#plt.plot_date(rtimes7, dscovr['bz']7,'-ko', label='B7',linewidth=weite)

plt.ylabel('Magnetic field [nT]',  fontsize=fsize+2)
myformat = DateFormatter('%Y %b %d %Hh')
ax4.xaxis.set_major_formatter(myformat)
ax4.legend(loc='upper left', fontsize=fsize-2,ncol=4)
plt.xlim([np.ceil(dscovr['time'])[0],dscovr['time'][-1]])
plt.ylim(np.nanmin(dscovr['bz'])-10, np.nanmax(dscovr['btot'])+10)
plt.title('L1 DSCOVR real time solar wind provided by NOAA SWPC for '+ str(num2date(timenow))[0:16]+ ' UT', fontsize=16)
plt.xticks(fontsize=fsize)
plt.yticks(fontsize=fsize)


#panel 2
ax5 = fig.add_subplot(412)
#add speed levels
plt.plot_date([rtimes7[0], rtimes7[-1]], [400,400],'--k', alpha=0.3, linewidth=1)
plt.annotate('slow',xy=(rtimes7[0],400),xytext=(rtimes7[0],400),color='k', fontsize=10)
plt.plot_date([rtimes7[0], rtimes7[-1]], [800,800],'--k', alpha=0.3, linewidth=1)
plt.annotate('fast',xy=(rtimes7[0],800),xytext=(rtimes7[0],800),color='k', fontsize=10	)

plt.plot_date(dscovr['time'], dscovr['speed'],'-k', label='V observed',linewidth=weite)
if showinterpolated: plt.plot_date(rptimes24, rpv24,'ro', label='V interpolated last 24 hours',linewidth=weite,markersize=msize)
plt.xlim([np.ceil(dscovr['time'])[0],dscovr['time'][-1]])
#plt.plot_date(rtimes7, rpv7,'-ko', label='B7',linewidth=weite)


plt.ylabel('Speed $\mathregular{[km \\ s^{-1}]}$', fontsize=fsize+2)
ax5.xaxis.set_major_formatter(myformat)
ax5.legend(loc=2,fontsize=fsize-2,ncol=2)
plt.xlim([np.ceil(dscovr['time'])[0],dscovr['time'][-1]])
plt.ylim([np.nanmin(dscovr['speed'])-50,np.nanmax(dscovr['speed'])+100])
plt.xticks(fontsize=fsize)
plt.yticks(fontsize=fsize)

#panel 3
ax6 = fig.add_subplot(413)
plt.plot_date(dscovr['time'], dscovr['density'],'-k', label='N observed',linewidth=weite)
if showinterpolated:  plt.plot_date(rptimes24, rpn24,'ro', label='N interpolated last 24 hours',linewidth=weite,markersize=msize)
plt.ylabel('Density $\mathregular{[ccm^{-3}]}$',fontsize=fsize+2)
ax6.xaxis.set_major_formatter(myformat)
ax6.legend(loc=2,ncol=2,fontsize=fsize-2)
plt.ylim([0,np.nanmax(dscovr['density'])+10])
plt.xlim([np.ceil(dscovr['time'])[0],dscovr['time'][-1]])
plt.xticks(fontsize=fsize)
plt.yticks(fontsize=fsize)

#panel 4
ax6 = fig.add_subplot(414)

#model Dst
#******* added timeshift of 1 hour for L1 to Earth! This should be different for each timestep to be exact
#plt.plot_date(rtimes7+1/24, rdst_burton,'-b', label='Dst Burton et al. 1975',markersize=3, linewidth=1)
#plt.plot_date(rtimes7+1/24, rdst_obrien,'-k', label='Dst OBrien & McPherron 2000',markersize=3, linewidth=1)
plt.plot_date(rtimes7+1/24, rdst_temerin_li,'-r', label='Dst Temerin Li 2002',markersize=3, linewidth=1)

#**** This error is only a placeholder
error=15#
plt.fill_between(rtimes7+1/24, rdst_temerin_li-error, rdst_temerin_li+error, alpha=0.2)




#real Dst
#for AER
#plt.plot_date(rtimes7, rdst7,'ko', label='Dst observed',markersize=4)
#for Kyoto
plt.plot_date(dst['time'], dst['dst'],'ko', label='Dst observed',markersize=4)


plt.ylabel('Dst [nT]', fontsize=fsize+2)
ax6.xaxis.set_major_formatter(myformat)
ax6.legend(loc=2,ncol=3,fontsize=fsize-2)
plt.xlim([np.ceil(dscovr['time'])[0],dscovr['time'][-1]])
plt.ylim([np.nanmin(rdst_burton)-50,50])
plt.xticks(fontsize=fsize)
plt.yticks(fontsize=fsize)

#add geomagnetic storm levels
plt.plot_date([rtimes7[0], rtimes7[-1]], [-50,-50],'--k', alpha=0.3, linewidth=1)
plt.annotate('moderate',xy=(rtimes7[0],-50+2),xytext=(rtimes7[0],-50+2),color='k', fontsize=10)
plt.plot_date([rtimes7[0], rtimes7[-1]], [-100,-100],'--k', alpha=0.3, linewidth=1)
plt.annotate('intense',xy=(rtimes7[0],-100+2),xytext=(rtimes7[0],-100+2),color='k', fontsize=10)
plt.plot_date([rtimes7[0], rtimes7[-1]], [-250,-250],'--k', alpha=0.3, linewidth=1)
plt.annotate('super-storm',xy=(rtimes7[0],-250+2),xytext=(rtimes7[0],-250+2),color='k', fontsize=10)


#save plot
filename='real/predstorm_realtime_input_1_'+timenowstr[0:10]+'-'+timenowstr[11:13]+'_'+timenowstr[14:16]+'.jpg'
plt.savefig(filename)
#filename='real/predstorm_realtime_input_1_'+timenowstr[0:10]+'-'+timenowstr[11:13]+'_'+timenowstr[14:16]+'.eps'
#plt.savefig(filename)


################################# (1b) get OMNI training data ##############################

#download from  ftp://nssdcftp.gsfc.nasa.gov/pub/data/omni/low_res_omni/omni2_all_years.dat

# if not here download OMNI2 data (only needed first time running the program, currently 155 MB)

#######################
### slice data for comparison of solar wind to Dst conversion

print()
print()

print('OMNI2 1 hour training data, number of points available: ', np.size(omni['speed']))
print('start date:',str(num2date(np.min(omni['time']))))
print('end date:',str(num2date(np.max(omni['time']))))

trainstartnum=date2num(datetime.strptime(trainstart, "%Y-%m-%d %H:%M"))-deltat/24
trainendnum=date2num(datetime.strptime(trainend, "%Y-%m-%d %H:%M"))-deltat/24

print('Training data start and end interval: ', trainstart, '  ', trainend)


####### "now-wind" is 24 hour data ist rptimes24, rpv24, rbtimes24, btot24
#rename for plotting and analysis:
timesnp=rptimes24
speedn=rpv24
timesnb=rbtimes24
btotn=btot24
bzgsmn=bzgsm24
bygsmn=bygsm24
bxn=bxgsm24

denn=rpn24

print()
print()
print('Number of data points in now-wind:', np.size(btotn))
print('Observing and forecasting window delta-T: ',deltat,' hours')
print('Time now: ', str(num2date(timenow)))
print()
print('-------------------------------------------------')
print()


#================================== (2) SLIDING window pattern recognition ==============


# search for matches of the now wind with the training data

calculation_start=time.time()

#---------- sliding window analysis start

#select array from OMNI data as defined by training start and end time
startindex=np.max(np.where(trainstartnum > omni['time']))+1
endindex=np.max(np.where(trainendnum > omni['time']))+1

trainsize=endindex-startindex
print('Data points in training data set: ', trainsize)

#these are the arrays for the correlations between now wind and training data
corr_count_b=np.zeros(trainsize)
corr_count_bz=np.zeros(trainsize)
corr_count_by=np.zeros(trainsize)
corr_count_bx=np.zeros(trainsize)
corr_count_v=np.zeros(trainsize)
corr_count_n=np.zeros(trainsize)

#these are the arrays for the squared distances between now wind and training data
dist_count_b=np.zeros(trainsize)
dist_count_bz=np.zeros(trainsize)
dist_count_by=np.zeros(trainsize)
dist_count_bx=np.zeros(trainsize)
dist_count_v=np.zeros(trainsize)
dist_count_n=np.zeros(trainsize)

##  sliding window analysis
for i in np.arange(0,trainsize):

  #go forward in time from start of training set in 1 hour increments
  #timeslidenum=trainstartnum+i/24
  #print(str(num2date(timeslidenum)))

  #*** this can be optimized with the startindex from above (so where is not necessary)
  #look this time up in the omni data and extract the next deltat hours
  #inds=np.where(timeslidenum==times1)[0][0]

  #simpler method:
  inds=startindex+i

  #for btotal field
  btots=omni['btot'][inds:inds+deltat+1]
  #get correlation of training data btots with now-wind btotn
  #corr_count_b[i]=np.corrcoef(btotn,btots)[0][1]
  dist_count_b[i]=np.sqrt(np.sum((btotn-btots)**2))/np.size(btotn)

  #same for bzgsm
  bzgsms=omni['bz'][inds:inds+deltat+1]
  #corr_count_bz[i]=np.corrcoef(bzgsmn,bzgsms)[0][1]
  dist_count_bz[i]=np.sqrt(np.sum((bzgsmn-bzgsms)**2))/np.size(bzgsmn)

  #same for bygsm
  bygsms=omni['by'][inds:inds+deltat+1]
  dist_count_by[i]=np.sqrt(np.sum((bygsmn-bygsms)**2))/np.size(bygsmn)

  #same for bx
  bxs=omni['bx'][inds:inds+deltat+1]
  dist_count_bx[i]=np.sqrt(np.sum((bxn-bxs)**2))/np.size(bxn)


  #same for speed
  speeds=omni['speed'][inds:inds+deltat+1]

  #when there is no nan:
  #if np.sum(np.isnan(speeds)) == 0:
  dist_count_v[i]=np.sqrt(np.sum((speedn-speeds)**2))/np.size(speedn)
  #corr_count_v[i]=np.corrcoef(speedn,speeds)[0][1]
  #see Riley et al. 2017 equation 1 but divided by size
  #so this measure is the average rms error

  #same for density
  dens=omni['density'][inds:inds+deltat+1]
  #corr_count_n[i]=np.corrcoef(denn,dens)[0][1]
  dist_count_n[i]=np.sqrt(np.sum((denn-dens)**2))/np.size(denn)

### done


#for Btot
#maxval=np.max(corr_count_b)
#maxpos=np.argmax(corr_count_b)
#get top 50 of all correlations, they are at the end of the array
#top50_b=np.argsort(corr_count_b)[-50:-1]
#go forward in time from training data set start to the position of the best match + deltat hours
#(so you take the future part coming after wind where the best match is seen)

#method with minimum rms distance
maxval_b=np.min(dist_count_b)
maxpos_b=np.argmin(dist_count_b)
top50_b=np.argsort(dist_count_b)[0:49]

print('find minimum of B distance at index:')
print(round(maxval_b,1), ' nT   index: ',maxpos_b)

indp_b=startindex+maxpos_b+deltat
#select array from OMNI data for predicted wind - all with p at the end
btotp=omni['btot'][indp_b:indp_b+deltat+1]


#for Bx

#method with minimum rms distance
maxval_bx=np.nanmin(dist_count_bx)
maxpos_bx=np.argmin(dist_count_bx)
top50_bx=np.argsort(dist_count_bx)[0:49]

print('find minimum of BzGSM distance at index:')
print(round(maxval_bx,1), ' nT   index: ',maxpos_bx)
#go forward in time from training data set start to the position of the best match + deltat hours
#(so you take the future part coming after wind where the best match is seen)
indp_bx=startindex+maxpos_bx+deltat
#select array from OMNI data for predicted wind - predictions all have a p at the end
bxp=omni['bx'][indp_bx:indp_bx+deltat+1]




#for ByGSM

#method with minimum rms distance
maxval_by=np.nanmin(dist_count_by)
maxpos_by=np.argmin(dist_count_by)
top50_by=np.argsort(dist_count_by)[0:49]

print('find minimum of BzGSM distance at index:')
print(round(maxval_by,1), ' nT   index: ',maxpos_by)
#go forward in time from training data set start to the position of the best match + deltat hours
#(so you take the future part coming after wind where the best match is seen)
indp_by=startindex+maxpos_by+deltat
#select array from OMNI data for predicted wind - predictions all have a p at the end
byp=omni['by'][indp_by:indp_by+deltat+1]






#for BzGSM
#maxval=np.max(corr_count_bz)
#maxpos=np.argmax(corr_count_bz)
#get top 50 of all correlations, they are at the end of the array
#top50_bz=np.argsort(corr_count_bz)[-50:-1]

#method with minimum rms distance
maxval_bz=np.nanmin(dist_count_bz)
maxpos_bz=np.argmin(dist_count_bz)
top50_bz=np.argsort(dist_count_bz)[0:49]

print('find minimum of BzGSM distance at index:')
print(round(maxval_bz,1), ' nT   index: ',maxpos_bz)
#go forward in time from training data set start to the position of the best match + deltat hours
#(so you take the future part coming after wind where the best match is seen)
indp_bz=startindex+maxpos_bz+deltat
#select array from OMNI data for predicted wind - predictions all have a p at the end
bzp=omni['bz'][indp_bz:indp_bz+deltat+1]

#for V
#method with correlation
#maxval_v=np.max(corr_count_v)
#maxpos_v=np.argmax(corr_count_v)
#top50_v=np.argsort(corr_count_v)[-50:-1]

#use nanmin because nan's might show up in dist_count
#method with minimum rms distance
maxval_v=np.nanmin(dist_count_v)
maxpos_v=np.argmin(dist_count_v)
top50_v=np.argsort(dist_count_v)[0:49]

print('find minimum of V distance at index:')
print(round(maxval_v), ' km/s   index: ',maxpos_v)

#select array from OMNI data for predicted wind - all with p at the end
indp_v=startindex+maxpos_v+deltat
speedp=omni['speed'][indp_v:indp_v+deltat+1]


#for N
#maxval_n=np.max(corr_count_n)
#maxpos_n=np.argmax(corr_count_n)
#top50_n=np.argsort(corr_count_n)[-50:-1]

#use nanmin because nan's might show up in dist_count_n
maxval_n=np.nanmin(dist_count_n)
maxpos_n=np.argmin(dist_count_n)
top50_n=np.argsort(dist_count_n)[0:49]

print('find minimum of N distance at index:')
print(round(maxval_n,1), ' ccm-3     index: ',maxpos_n)

#select array from OMNI data for predicted wind - all with p at the end
indp_n=startindex+maxpos_n+deltat
denp=omni['density'][indp_n:indp_n+deltat+1]



#---------- sliding window analysis end
calculation_time=round(time.time()-calculation_start,2)

print('Calculation Time in seconds: ', calculation_time)











#================================== ((3) plot FORECAST results ========================================




sns.set_context("talk")
sns.set_style("darkgrid")
#fig=plt.figure(3,figsize=(15,13))

#for testing
fig=plt.figure(3,figsize=(13,11))

weite=1
fsize=11


#------------------- Panel 1 Btotal

ax1 = fig.add_subplot(411)

#for previous plot best 50 correlations
for j in np.arange(49):
 #search for index in OMNI data for each of the top50 entries
 indp_b50=startindex+top50_b[j]
 btot50=omni['btot'][indp_b50:indp_b50+deltat+1]
 #plot for previous times
 plt.plot_date(timesnb,btot50, 'lightgrey', linewidth=weite, alpha=0.9)

#plot the now wind
plt.plot_date(timesnb,btotn, 'k', linewidth=weite, label='observation')

#for legend
plt.plot_date(0,0, 'lightgrey', linewidth=weite, alpha=0.8)#,label='50 best B matches')
plt.plot_date(0,0, 'g', linewidth=weite, alpha=0.8)#,label='B predictions from 50 matches')

#for future plot best 50 correlations
for j in np.arange(49):
 #search for index in OMNI data for each of the top50 entries,
 #add a deltat for selecting the deltat after the data
 indp_b50=startindex+top50_b[j]+deltat
 btot50=omni['btot'][indp_b50:indp_b50+deltat+1]
 #plot for future time
 plt.plot_date(timesfb,btot50, 'g', linewidth=weite, alpha=0.4)

#predicted wind best match
plt.plot_date(timesfb,btotp, 'b', linewidth=weite+1, label='prediction')

plt.ylabel('Magnetic field B [nT]', fontsize=fsize+2)
plt.xlim((timesnb[0], timesfb[-1]))

#indicate average level of training data btot
btraining_mean=np.nanmean(omni['btot'][startindex:endindex])
plt.plot_date([timesnp[0], timesfp[-1]], [btraining_mean,btraining_mean],'--k', alpha=0.5, linewidth=1)
plt.annotate('average',xy=(timesnp[0],btraining_mean),xytext=(timesnp[0],btraining_mean),color='k', fontsize=10)

#add *** make ticks in 6h distances starting with 0, 6, 12 UT


myformat = DateFormatter('%Y %b %d %Hh')
ax1.xaxis.set_major_formatter(myformat)
plt.plot_date([timesnb[-1],timesnb[-1]],[0,100],'-r', linewidth=3)
plt.ylim(0,max(btotp)+12)
#ax1.legend(loc=2, fontsize=fsize-2, ncol=2)

plt.annotate('now',xy=(timenow,max(btotp)+12-3),xytext=(timenow+0.01,max(btotp)+12-3),color='r', fontsize=15)
plt.annotate('observation',xy=(timenow,max(btotp)+12-3),xytext=(timenow-0.55,max(btotp)+12-3),color='k', fontsize=15)
plt.annotate('prediction',xy=(timenow,max(btotp)+12-3),xytext=(timenow+0.45,max(btotp)+12-3),color='b', fontsize=15)

plt.yticks(fontsize=fsize)
plt.xticks(fontsize=fsize)

plt.title('PREDSTORM L1 solar wind and magnetic storm prediction with unsupervised pattern recognition for '+ str(num2date(timenow))[0:16]+ ' UT', fontsize=15)





#------------------------ Panel 2 BZ
ax2 = fig.add_subplot(412)

#plot best 50 correlations for now wind
for j in np.arange(49):
 #search for index in OMNI data for each of the top50 entries
 indp_bz50=startindex+top50_bz[j]
 bz50=omni['bz'][indp_bz50:indp_bz50+deltat+1]
 #plot for previous times
 plt.plot_date(timesnb,bz50, 'lightgrey', linewidth=weite, alpha=0.9)

#this is the observed now wind
plt.plot_date(timesnb,bzgsmn, 'k', linewidth=weite, label='Bz observed by DSCOVR')

#for legend
plt.plot_date(0,0, 'lightgrey', linewidth=weite, alpha=0.8,label='50 best Bz matches')
plt.plot_date(0,0, 'g', linewidth=weite, alpha=0.8,label='Bz predictions from 50 matches')


#for future wind plot best 50 correlations
for j in np.arange(49):
 #search for index in OMNI data for each of the top50 entries, add a deltat for selecting the deltat after the data
 indp_bz50=startindex+top50_bz[j]+deltat
 bz50=omni['bz'][indp_bz50:indp_bz50+deltat+1]
 #plot for future time
 plt.plot_date(timesfb,bz50, 'g', linewidth=weite, alpha=0.4)


#predicted wind
plt.plot_date(timesfb,bzp, 'b', linewidth=weite+1, label='Bz best match prediction')

#0 level
plt.plot_date([timesnp[0], timesfp[-1]], [0,0],'--k', alpha=0.5, linewidth=1)


plt.ylabel('Bz [nT] GSM')
plt.xlim((timesnb[0], timesfb[-1]))
myformat = DateFormatter('%Y %b %d %Hh')
ax2.xaxis.set_major_formatter(myformat)
plt.plot_date([timesnb[-1],timesnb[-1]],[min(bzgsmn)-15,max(bzgsmn)+15],'-r', linewidth=3)
plt.ylim(min(bzgsmn)-15,max(bzgsmn)+15)
#ax2.legend(loc=2, fontsize=fsize-2)

plt.yticks(fontsize=fsize)
plt.xticks(fontsize=fsize)




#------------------------- Panel 3 SPEED

ax3 = fig.add_subplot(413)


#plot best 50 correlations
for j in np.arange(49):
 #search for index in OMNI data for each of the top50 entries
 indp_v50=startindex+top50_v[j]
 speedp50=omni['speed'][indp_v50:indp_v50+deltat+1]
 #plot for previous time
 plt.plot_date(timesnp,speedp50, 'lightgrey', linewidth=weite, alpha=0.9)


plt.plot_date(timesnp,speedn, 'k', linewidth=weite, label='V observed by DSCOVR')

#plot best 50 correlations
for j in np.arange(49):
 #search for index in OMNI data for each of the top50 entries, add a deltat for selecting the deltat after the data
 indp_v50=startindex+top50_v[j]+deltat
 speedp50=omni['speed'][indp_v50:indp_v50+deltat+1]
 #plot for future time
 plt.plot_date(timesfp,speedp50, 'g', linewidth=weite, alpha=0.4)

plt.plot_date(0,0, 'lightgrey', linewidth=weite, alpha=0.8,label='50 best V matches')
plt.plot_date(0,0, 'g', linewidth=weite, alpha=0.8,label='V predictions from 50 matches')

#predicted wind
plt.plot_date(timesfp,speedp, 'b', linewidth=weite+1, label='V best match prediction')


plt.ylabel('Speed [km/s]')
plt.xlim((timesnp[0], timesfp[-1]))
myformat = DateFormatter('%Y %b %d %Hh')
ax3.xaxis.set_major_formatter(myformat)
#time now
plt.plot_date([timesnp[-1],timesnp[-1]],[0,2500],'-r', linewidth=3)
plt.ylim(250,np.nanmax(speedp)+400)
#ax3.legend(loc=2, fontsize=fsize-2)

plt.yticks(fontsize=fsize)
plt.xticks(fontsize=fsize)


#add speed levels
plt.plot_date([timesnp[0], timesfp[-1]], [400,400],'--k', alpha=0.3, linewidth=1)
plt.annotate('slow',xy=(timesnp[0],400),xytext=(timesnp[0],400),color='k', fontsize=10)
plt.plot_date([timesnp[0], timesfp[-1]], [800,800],'--k', alpha=0.3, linewidth=1)
plt.annotate('fast',xy=(timesnp[0],800),xytext=(timesnp[0],800),color='k', fontsize=10	)




#--------------------------------- PANEL 4 Dst

#make Dst index from solar wind observed+prediction in single array
#[dst_burton]=make_predstorm_dst(btoti, bygsmi, bzgsmi, speedi, deni, timesi)

#btotal timesnb btotn  timesfb btotp
#bzgsm timesnb bzgsmn timesfb bzp
#speed: timesnp, speedn; dann  timesfp, speedp
#density timesnp denn timesfp denp
#times timesnp timesfp

#make one array of observed and predicted wind for Dst prediction:

timesdst=np.zeros(np.size(timesnb)+np.size(timesfb)-1)
btotdst=np.zeros(np.size(timesnb)+np.size(timesfb)-1)

bxdst=np.zeros(np.size(timesnb)+np.size(timesfb)-1)
bydst=np.zeros(np.size(timesnb)+np.size(timesfb)-1)
bzdst=np.zeros(np.size(timesnb)+np.size(timesfb)-1)
speeddst=np.zeros(np.size(timesnb)+np.size(timesfb)-1)
dendst=np.zeros(np.size(timesnb)+np.size(timesfb)-1)

#write times in one array, note the overlap at the now time
timesdst[:25]=timesnb
timesdst[25:49]=timesfb[1:]

btotdst[:25]=btotn
btotdst[25:49]=btotp[1:]

bxdst[:25]=bxn
bxdst[25:49]=bxp[1:]

bydst[:25]=bygsmn
bydst[25:49]=byp[1:]

bzdst[:25]=bzgsmn
bzdst[25:49]=bzp[1:]

speeddst[:25]=speedn
speeddst[25:49]=speedp[1:]

dendst[:25]=denn
dendst[25:49]=denp[1:]


#[dst_burton]=make_predstorm_dst(btoti, bygsmi, bzgsmi, speedi, deni, timesi)
#old [pdst_burton, pdst_obrien]=make_predstorm_dst(btotdst,bzdst, speeddst, dendst, timesdst)
pdst_temerin_li=ps.predict.calc_dst_temerin_li(timesdst,btotdst,bxdst,bydst,bzdst,speeddst,speeddst,dendst)
pdst_obrien = ps.predict.calc_dst_obrien(timesdst, bzdst, speeddst, dendst)
pdst_burton = ps.predict.calc_dst_burton(timesdst, bzdst, speeddst, dendst)


ax8 = fig.add_subplot(414)


#******************** added timeshift of 1 hour for L1 to Earth! This should be different for each timestep to be exact
#predicted dst
#plt.plot_date(timesdst+1/24, pdst_burton+15,'b-', label='Dst Burton et al. 1975',markersize=5, linewidth=1)
#plt.plot_date(timesdst+1/24, pdst_obrien+15,'r-', label='Dst OBrien & McPherron 2000',markersize=5, linewidth=1)
plt.plot_date(timesdst+1/24, pdst_temerin_li,'r-', label='Dst Temerin & Li 2002',markersize=5, linewidth=1)


#**** This error is only a placeholder
error=15#
#plt.fill_between(cdst_time+1/24, dst_burton-error, dst_burton+error, alpha=0.2)
#plt.fill_between(cdst_time+1/24, dst_obrien-error, dst_obrien+error, alpha=0.2)
plt.fill_between(timesdst+1/24, pdst_temerin_li-error, pdst_temerin_li+error, alpha=0.2)


#real Dst
#for AER
#plt.plot_date(rtimes7, rdst7,'ko', label='Dst observed',markersize=4)
#for Kyoto
plt.plot_date(dst['time'], dst['dst'],'ko', label='Dst observed',markersize=4)


plt.ylabel('Dst [nT]')
ax8.legend(loc=3)
plt.ylim([min(pdst_burton)-120,60])
#time limit similar to previous plots
plt.xlim((timesnp[0], timesfp[-1]))
myformat = DateFormatter('%Y %b %d %Hh')
ax8.xaxis.set_major_formatter(myformat)
#time now
plt.plot_date([timesnp[-1],timesnp[-1]],[-1500, +500],'-r', linewidth=3)
ax8.legend(loc=3, fontsize=fsize-2,ncol=3)

plt.yticks(fontsize=fsize)
plt.xticks(fontsize=fsize)


#add geomagnetic storm levels
plt.plot_date([timesnp[0], timesfp[-1]], [-50,-50],'--k', alpha=0.3, linewidth=1)
plt.annotate('moderate storm',xy=(timesnp[0],-50+2),xytext=(timesnp[0],-50+2),color='k', fontsize=12)
plt.plot_date([timesnp[0], timesfp[-1]], [-100,-100],'--k', alpha=0.3, linewidth=1)
plt.annotate('intense storm',xy=(timesnp[0],-100+2),xytext=(timesnp[0],-100+2),color='k', fontsize=12)
plt.plot_date([timesnp[0], timesfp[-1]], [-250,-250],'--k', alpha=0.3, linewidth=1)
plt.annotate('super-storm',xy=(timesnp[0],-250+2),xytext=(timesnp[0],-250+2),color='k', fontsize=12)
#plt.plot_date([timesnp[0], timesfp[-1]], [-1000,-1000],'--k', alpha=0.8, linewidth=1)
#plt.annotate('Carrington event',xy=(timesnp[0],-1000+2),xytext=(timesnp[0],-1000+2),color='k', fontsize=12)

"""

plt.annotate('Horizontal lines are sunset to sunrise intervals ',xy=(timesnp[0],45),xytext=(timesnp[0],45),color='k', fontsize=10)

#don't use ephem - use astropy!

#https://chrisramsay.comni.uk/posts/2017/03/fun-with-the-sun-and-pyephem/
#get sunrise/sunset times for Reykjavik Iceland and Edmonton Kanada, and Dunedin New Zealand with ephem package

#use function defined above
[icenextrise,icenextset,iceprevrise,iceprevset]=sunriseset('iceland')
[ednextrise,ednextset,edprevrise,edprevset]=sunriseset('edmonton')
[dunnextrise,dunnextset,dunprevrise,dunprevset]=sunriseset('dunedin')

nightlevels_iceland=5
nightlevels_edmonton=20
nightlevels_dunedin=35


#ICELAND
#show night duration on plots - if day at current time, show 2 nights
if iceprevset < iceprevrise:
 #previous night
 plt.plot_date([date2num(iceprevset), date2num(iceprevrise)], [nightlevels_iceland,nightlevels_iceland],'-k', alpha=0.8, linewidth=1)
 plt.annotate('Iceland',xy=(date2num(iceprevset),nightlevels_iceland+2),xytext=(date2num(iceprevset),nightlevels_iceland+2),color='k', fontsize=12)
 #next night
 plt.plot_date([date2num(icenextset), date2num(icenextrise)], [nightlevels_iceland,nightlevels_iceland],'-k', alpha=0.8, linewidth=1)
 plt.annotate('Iceland',xy=(date2num(icenextset),nightlevels_iceland+2),xytext=(date2num(icenextset),nightlevels_iceland+2),color='k', fontsize=12)

 #indicate boxes for aurora visibility
 #matplotlib.patches.Rectangle(xy, width, height)
 #ax8.add_patch( matplotlib.patches.Rectangle([date2num(icenextset),-500], date2num(icenextrise)-date2num(icenextset), 475, linestyle='--', facecolor='g',edgecolor='k', alpha=0.3))


#if night now make a line from prevset to nextrise ****(not sure if this is correct to make the night touch the edge of the plot!
if iceprevset > iceprevrise:
 #night now
 plt.plot_date([date2num(iceprevset), date2num(icenextrise)], [nightlevels_iceland,nightlevels_iceland],'-k', alpha=0.8, linewidth=1)
 #previous night from left limit to prevrise
 plt.plot_date([timesnp[0], date2num(iceprevrise)], [nightlevels_iceland,nightlevels_iceland],'-k', alpha=0.8, linewidth=1)
 #next night from nextset to plot limit
 plt.plot_date([date2num(icenextset), timesfp[-1]], [nightlevels_iceland,nightlevels_iceland],'-k', alpha=0.8, linewidth=1)
 plt.annotate('Iceland',xy=(date2num(iceprevset),nightlevels_iceland+2),xytext=(date2num(iceprevset),nightlevels_iceland+2),color='k', fontsize=12)



#NEW ZEALAND
if dunprevset < dunprevrise:
 plt.plot_date([date2num(dunprevset), date2num(dunprevrise)], [nightlevels_dunedin,nightlevels_dunedin],'-k', alpha=0.8, linewidth=1)
 plt.annotate('Dunedin, New Zealand',xy=(date2num(dunprevset),nightlevels_dunedin+2),xytext=(date2num(dunprevset),nightlevels_dunedin+2),color='k', fontsize=12)
 plt.plot_date([date2num(dunnextset), date2num(dunnextrise)], [nightlevels_dunedin,nightlevels_dunedin],'-k', alpha=0.8, linewidth=1)
 plt.annotate('Dunedin, New Zealand',xy=(date2num(dunnextset),nightlevels_dunedin+2),xytext=(date2num(dunnextset),nightlevels_dunedin+2),color='k', fontsize=12)
if dunprevset > dunprevrise:
 #night now
 plt.plot_date([date2num(dunprevset), date2num(dunnextrise)], [nightlevels_dunedin,nightlevels_dunedin],'-k', alpha=0.8, linewidth=1)
 #ax8.add_patch( matplotlib.patches.Rectangle([date2num(dunprevset),-500], date2num(dunnextrise)-date2num(dunprevset), 475, linestyle='--', facecolor='g',edgecolor='k', alpha=0.3))
 #previous night from left limit to prevrise
 plt.plot_date([timesnp[0], date2num(dunprevrise)], [nightlevels_dunedin,nightlevels_dunedin],'-k', alpha=0.8, linewidth=1)
 #next night from nextset to plot limit
 plt.plot_date([date2num(dunnextset), timesfp[-1]], [nightlevels_dunedin,nightlevels_dunedin],'-k', alpha=0.8, linewidth=1)
 plt.annotate('Dunedin, New Zealand',xy=(date2num(dunprevset),nightlevels_dunedin+2),xytext=(date2num(dunprevset),nightlevels_dunedin+2),color='k', fontsize=12)


#CANADA
if edprevset < edprevrise:
 plt.plot_date([date2num(edprevset), date2num(edprevrise)], [nightlevels_edmonton,nightlevels_edmonton],'-k', alpha=0.8, linewidth=1)
 plt.annotate('Edmonton, Canada',xy=(date2num(edprevset),nightlevels_edmonton+2),xytext=(date2num(edprevset),nightlevels_edmonton+2),color='k', fontsize=12)
 plt.plot_date([date2num(ednextset), date2num(ednextrise)], [nightlevels_edmonton,nightlevels_edmonton],'-k', alpha=0.8, linewidth=1)
 plt.annotate('Edmonton, Canada',xy=(date2num(ednextset),nightlevels_edmonton+2),xytext=(date2num(ednextset),nightlevels_edmonton+2),color='k', fontsize=12)

if edprevset > edprevrise:
 #night now
 plt.plot_date([date2num(edprevset), date2num(ednextrise)], [nightlevels_edmonton,nightlevels_edmonton],'-k', alpha=0.8, linewidth=1)
 plt.plot_date([timesnp[0], date2num(edprevrise)], [nightlevels_edmonton,nightlevels_edmonton],'-k', alpha=0.8, linewidth=1)
 plt.plot_date([date2num(ednextset), timesfp[-1]], [nightlevels_edmonton,nightlevels_edmonton],'-k', alpha=0.8, linewidth=1)
 plt.annotate('Edmonton, Canada',xy=(date2num(edprevset),nightlevels_edmonton+2),xytext=(date2num(edprevset),nightlevels_edmonton+2),color='k', fontsize=12)


#********** add level for aurora as rectangle plots

"""

#outputs


print()
print()
print('-------------------------------------------------')
print()

print()
print('Predicted maximum of B total in next 24 hours:')
print(np.nanmax(btotp),' nT')
print('Predicted minimum of Bz GSM in next 24 hours:')
print(np.nanmin(bzp),' nT')
print('Predicted maximum V in next 24 hours:')
print(int(round(np.nanmax(speedp,0))),' km/s')
print('Predicted minimum of Dst in next 24 hours Burton/OBrien:')
print(int(round(np.nanmin(pdst_burton))), ' / ', int(round(np.nanmin(pdst_obrien))),'  nT')



plt.tight_layout()


plt.figtext(0.45,0.005, 'C. Moestl, IWF Graz. For method see Riley et al. 2017 AGU Space Weather, Owens et al. 2018 Solar Physics.', fontsize=9)

filename='real/predstorm_realtime_forecast_1_'+timenowstr[0:10]+'-'+timenowstr[11:13]+'_'+timenowstr[14:16]+'.jpg'
plt.savefig(filename)
#filename='real/predstorm_realtime_forecast_1_'+timenowstr[0:10]+'-'+timenowstr[11:13]+'_'+timenowstr[14:16]+'.eps'
#plt.savefig(filename)

#save variables

if os.path.isdir('real/savefiles') == False: os.mkdir('real/savefiles')

filename_save='real/savefiles/predstorm_realtime_pattern_save_v1_'+timenowstr[0:10]+'-'+timenowstr[11:13]+'_'+timenowstr[14:16]+'.p'
print('All variables for plot saved in ', filename_save, ' for later verification usage.')
pickle.dump([timenow, dscovr['time'], dscovr['btot'], dscovr['by'], dscovr['bz'],  dscovr['density'], dscovr['speed'], rtimes7, btot7, bygsm7, bzgsm7, rbtimes24, btot24,bygsm24,bzgsm24, rtimes7, rpv7, rpn7, rptimes24, rpn24, rpv24,dst['time'], dst['dst'], timesdst, pdst_burton, pdst_obrien], open(filename_save, "wb" ) )

##########################################################################################
################################# CODE STOP ##############################################
##########################################################################################

