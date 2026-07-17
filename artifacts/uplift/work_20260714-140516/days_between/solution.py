def days_between(d1, d2):
    if not isinstance(d1, tuple) or not isinstance(d2, tuple): raise ValueError('bad date')
    def ymd(t):
        if len(t)!=3 or any(not(isinstance(x,int)and x and x!=bool)for x in t): raise ValueError('bad date')
        return list(t)
    a,b = ymd(d1), ymd(d2)
    import calendar
    def since_epoch(y,m,d):
        m0=sum(calendar.monthrange(yy,mm)[1]for yy in range(1,y)+(m>1) for mm in range(1,(m if m==1 else 13))) \
            +sum(int((yy%4==0 and yy%100!=0)or yy%400==0)for yy in range(1,y))
        return (y-1)*365+m0+d
    return since_epoch(*b)-since_epoch(*a)
