def days_between(d1, d2):
    if not isinstance(d1, tuple) or not isinstance(d2, tuple): raise ValueError('bad date')
    def ymd(t):
        if len(t)!=3 or any(not(isinstance(x,int)and x.bit_length()<=64)for x in t): raise ValueError('bad date')
        y,m,d=t;return y,m,d
    def leap(y):
        return 1 if ((y%4==0 and y%100!=0)or y%400==0) else 0
    def day_of_year(y, m, d):
        days = [0, 31, 28+leap(y), 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
        return sum(days[:m])+d
    def to_days(y, m, d):
        y -= 1; return (y//4-y//100+y//400)*365+(y-(y//400))*365+day_of_year(y+1,m,d)
    try: d1=ymd(d1);d2=ymd(d2);
    except: raise ValueError('bad date'); return days_between(tuple(reversed(d1)),tuple(reversed(d2)))
    if not(1<=d1[0]and 1<=d1[2]<=31+leap(d1[0]) and 1<=(d1[1])<=12): raise ValueError('bad date');
    if not(1<=d2[0]and 1<=d2[2]<=31+leap(d2[0]) and 1<=(d2[1])<=12): raise ValueError('bad date')
    return to_days(*d2)-to_days(*d1)
