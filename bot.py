print()

    print(
        "LONG ADAYLARI:",
        len(long_candidates)
    )

    for item in long_candidates:

        print(
            f"{item['symbol']:12} "
            f"SKOR={item['long_score']} "
            f"RSI={item['rsi']:.2f}"
        )

    # --------------------------------------------------------
    # SHORT ADAYLARI
    # --------------------------------------------------------

    print()

    print(
        "SHORT ADAYLARI:",
        len(short_candidates)
    )

    for item in short_candidates:

        print(
            f"{item['symbol']:12} "
            f"SKOR={item['short_score']} "
            f"RSI={item['rsi']:.2f}"
        )

    # --------------------------------------------------------
    # TELEGRAM
    # --------------------------------------------------------

    notification_window = (
        is_1h_notification_window()
    )

    print()

    print(
        "1H bildirim penceresi:",
        notification_window
    )

    messages_sent = 0

    if notification_window:

        # ----------------------------------------------------
        # EN FAZLA 5 LONG
        # ----------------------------------------------------

        for item in long_candidates[:5]:

            message = format_signal(
                item,
                "LONG"
            )

            if telegram_send(
                message
            ):

                messages_sent += 1

        # ----------------------------------------------------
        # EN FAZLA 5 SHORT
        # ----------------------------------------------------

        for item in short_candidates[:5]:

            message = format_signal(
                item,
                "SHORT"
            )

            if telegram_send(
                message
            ):

                messages_sent += 1

    else:

        print(
            "1H kapanış penceresi değil. "
            "Telegram mesajı gönderilmeyecek."
        )

    # --------------------------------------------------------
    # SONUÇ
    # --------------------------------------------------------

    print()

    print(
        "Telegram gönderilen sinyal:",
        messages_sent
    )

    print()

    print(
        "1H TARAMA TAMAMLANDI."
    )


# ============================================================
# PROGRAMI BAŞLAT
# ============================================================

if __name__ == "__main__":

    main()
