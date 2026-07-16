import yt_dlp


def download_authenticated_stream(m3u8_url, output_name="downloaded_video.mp4"):
    ydl_opts = {
        # Custom user-agent to pretend to be a real browser, preventing blocks
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        },
        'outtmpl': output_name,  # Output filename
        'quiet': False,  # Shows progress bar in terminal
    }

    print("Initializing download with yt-dlp...")
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            ydl.download([m3u8_url])
            print(f"\nSuccess! Video saved to {output_name}")
        except Exception as e:
            print(f"\nAn error occurred: {e}")


# Your full authenticated URL
stream_url = "https://dcs-vod.mp.lura.live/vod/p/master.m3u8?encp=EMoieJ9m4AyLa3D-8DB4pA:0o_8TyerjwoIRQI9FvK4iXEIBDSelgVEzGI7xLpBD9FNXXgRoYHeBTgRd_Z3-taADnuzNNnbnGYsJE6OvmdsZOCAdfbmjGlofkIG9AOCO0x46JnQ2s_P3M040PP9DWnTYsMzDf0z3TH2AlcR3uT4tgaxN3Lbr8DV6bV4wBGc1i4Muci4pVgEkpw_rbS7HmwCjWn39yT-uFs4lPRyECVSvZLinJu3XFAaWlzInok724Ip10O-2d-CqM5l-ewmZKgzVVfBKyJBhCotevWud282acRD9fpeNNgH6UON00D6adRPe8HV3g8F6Yr4eK6xo7WwxjBsCRgrU8S3t5t3sy0SCyPykaBSKXlUnk5aPEIU08BJ2bXF3jFwW9gQV53rvsaqP3-b7ezXc8yyIsmhYVhKImdtCHKi-LfAwB_amYQ7XX-tWT9ybukQjoFtVXe4N2wHQzH5ueNuW3hTif6xuXlGPV5GCJGLWf_BO6JT-zA6KVo&anvtrid=670a0934d07694f91c5b236f4b3a9c2b&anvauth=tb=0~te=1784143263~sgn=67eaaf3ee78f4d4d9361480dcdc6974c81a6adecd44e00c4053fffe379b8b228&t=1784143173"

download_authenticated_stream(stream_url)