import customtkinter as ctk
import tkinter as tk


def ask_choice(
    *,
    options: list[str],
    parent,
    title: str = "Sélection TMDB",
    width: int = 720,
    height: int = 420
) -> int:
    """
    Affiche une fenêtre de sélection et retourne l'index choisi (1-based).
    Retourne 0 si annulé.
    """
    ctk.set_appearance_mode("dark")

    # ==================================================
    # Fenêtre
    # ==================================================

    win = ctk.CTkToplevel(parent)
    win.title(title)
    win.geometry(f"{width}x{height}")
    win.grab_set()
    win.focus_set()
    win.transient(parent)

    frame = ctk.CTkFrame(win)
    frame.pack(fill="both", expand=True, padx=18, pady=18)

    header = ctk.CTkLabel(
        frame,
        text="Sélectionnez le bon résultat :",
        font=("Segoe UI", 17, "bold"),
        anchor="w"
    )
    header.pack(anchor="w", pady=(0, 14))

    # ==================================================
    # Zone scrollable
    # ==================================================

    scroll_zone = ctk.CTkFrame(frame, fg_color="transparent")
    scroll_zone.pack(fill="both", expand=True)

    canvas = tk.Canvas(
        scroll_zone,
        background="#232323",
        borderwidth=0,
        highlightthickness=0
    )
    scrollbar = tk.Scrollbar(
        scroll_zone,
        orient="vertical",
        command=canvas.yview
    )

    content = ctk.CTkFrame(canvas, fg_color="transparent")
    content.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )

    canvas.create_window((0, 0), window=content, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)

    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    # ==================================================
    # Options
    # ==================================================

    selected = tk.IntVar(value=1)

    for i, text in enumerate(options, start=1):
        container = ctk.CTkFrame(content, fg_color="transparent")
        container.pack(fill="x", padx=6, pady=10)

        # --- Séparation titre / détails ---
        lines = text.split("\n")
        title_line = lines[0]
        details = "\n".join(lines[1:])

        # --- RadioButton : texte court uniquement ---
        ctk.CTkRadioButton(
            container,
            text=("👉 " if i == 1 else "   ") + title_line,
            variable=selected,
            value=i,
            font=("Segoe UI", 14, "bold"),
            fg_color="#444",
            text_color="#FFFFFF"
        ).pack(anchor="w")

        # --- Label : texte long lisible ---
        if details.strip():
            ctk.CTkLabel(
                container,
                text=details,
                font=("Segoe UI", 13),
                text_color="#CCCCCC",
                wraplength=580,     # ✅ autorisé sur CTkLabel
                justify="left"
            ).pack(anchor="w", padx=(28, 0), pady=(4, 0))

    # ==================================================
    # Bouton validation
    # ==================================================

    ctk.CTkButton(
        frame,
        text="Valider",
        width=160,
        height=40,
        font=("Segoe UI", 15),
        command=lambda: [setattr(win, "result", selected.get()), win.destroy()]
    ).pack(pady=(18, 2))

    win.wait_window()
    return getattr(win, "result", 0)
