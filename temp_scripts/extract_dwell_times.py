import pydicom
from pathlib import Path

def get_correct_dwell_times(rtplan_file):
    """Extracts and calculates the correct dwell times from an RTPLAN file."""
    if not rtplan_file:
        return []
    ds = pydicom.dcmread(rtplan_file)
    dwell_times = []
    if hasattr(ds, 'ApplicationSetupSequence'):
        for app_setup in ds.ApplicationSetupSequence:
            if hasattr(app_setup, 'ChannelSequence'):
                for channel in app_setup.ChannelSequence:
                    channel_total_time = float(channel.ChannelTotalTime)
                    final_cumulative_time_weight = float(channel.FinalCumulativeTimeWeight)
                    if hasattr(channel, 'BrachyControlPointSequence'):
                        last_time_weight = 0.0
                        for cp in channel.BrachyControlPointSequence:
                            if hasattr(cp, 'CumulativeTimeWeight'):
                                current_time_weight = float(cp.CumulativeTimeWeight)
                                dwell_time_weight = current_time_weight - last_time_weight
                                if dwell_time_weight > 0:
                                    dwell_time = dwell_time_weight * channel_total_time / final_cumulative_time_weight
                                    dwell_times.append(dwell_time)
                                last_time_weight = current_time_weight
    return dwell_times

def main():
    rtplan_file = r"C:\Users\echorniak\GIT\BrachyD2ccEval\DOE^JANE_ANON93124_RTPLAN_2025-07-11_122839_HDR_GP.Wood_n1__00000\2.16.840.1.114362.1.12177026.23360333229.711517226.250.190.dcm"
    if not Path(rtplan_file).is_file():
        print(f"Error: File not found at {rtplan_file}")
        return

    dwell_times = get_correct_dwell_times(rtplan_file)

    if dwell_times:
        print("Dwell Times (s):")
        for i, time in enumerate(dwell_times):
            print(f"  Dwell Position {i+1}: {time:.4f}")
    else:
        print("No dwell times found in the provided RT Plan file.")

if __name__ == "__main__":
    main()
