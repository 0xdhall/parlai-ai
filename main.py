def is_match_now_to_6am(commence_time):
    """
    PERBAIKAN FINAL: Menggunakan datetime.now(timezone.utc) secara murni
    untuk mengunci waktu scan tepat 24 jam ke depan dari detik ini, 
    sehingga pertandingan malam ini sampai subuh tidak akan terlewat.
    """
    if not commence_time:
        return False, None

    try:
        if isinstance(commence_time, str):
            match_utc = datetime.fromisoformat(commence_time.replace("Z", "+00:00"))
        else:
            match_utc = datetime.fromtimestamp(commence_time, tz=timezone.utc)
    except:
        return False, None

    # Menggunakan datetime aware UTC secara penuh untuk menyamakan persepsi server vs API
    now_utc = datetime.now(timezone.utc)
    
    # Batas akhir pemindaian adalah 24 jam ke depan dari detik ini
    cutoff_utc = now_utc + timedelta(hours=24)

    # Loloskan jika pertandingan berada dalam rentang 24 jam ke depan
    is_allowed = now_utc <= match_utc <= cutoff_utc

    # Konversi hasil akhir ke WITA hanya untuk kebutuhan tampilan teks di Telegram
    match_wita = match_utc + timedelta(hours=8)

    return is_allowed, match_wita
