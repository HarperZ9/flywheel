// Merge overlapping intervals in ascending order of their start times
intervals = [[], []]; // Initialize two empty intervals arrays

// Iterate through each interval
for(int i = 0; i < intervals[0].length; ++i) {
    // If current interval starts before the previous end, merge it into the first interval array
    if (start < intervals[0][i]) 
        intervals[0] = [min(start, intervals[0][i]), max(end, intervals[0][i])];

    else if (intervals[1].length == 0) {
        // If no end in the second interval and first interval is empty
        intervals[1] = new Interval(intervals[0][i], intervals[0][i]);
    }   
}

// Convert the first array to a sorted list of intervals
ranges = new List<Interval>();

for(int i = 0; i < intervals.length; ++i) {
    int start = intervals[i][0];
    int end = intervals[i][1];

    // If there is no previous or current interval, insert it into the result
    if (start == end)
        ranges.Add(new Interval(start, end));
}

// Return the list of merged and sorted intervals
return new List<Interval>(ranges);
