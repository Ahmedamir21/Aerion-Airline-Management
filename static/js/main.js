// Small UI helpers
document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.auth-form, .search-form').forEach(function (form) {
        form.addEventListener('submit', function (e) {
            var ok = true;
            form.querySelectorAll('[required]').forEach(function (input) {
                if (!input.value.trim()) {
                    ok = false;
                    input.style.borderColor = 'var(--bad-fg)';
                } else {
                    input.style.borderColor = '';
                }
            });
            if (!ok) e.preventDefault();
        });
    });

    var origin = document.querySelector('select[name="origin"]');
    var dest = document.querySelector('select[name="destination"]');
    if (origin && dest) {
        origin.closest('form').addEventListener('submit', function (e) {
            if (origin.value && origin.value === dest.value) {
                e.preventDefault();
                alert('Origin and destination must be different.');
            }
        });
    }
});

// Swap origin and destination on the landing search card
document.addEventListener('DOMContentLoaded', function () {
    var swap = document.getElementById('swap');
    if (!swap) return;
    swap.addEventListener('click', function () {
        var o = document.querySelector('select[name="origin"]');
        var d = document.querySelector('select[name="destination"]');
        var t = o.value; o.value = d.value; d.value = t;
    });
});

// Show or hide a password field (works for every .pw-toggle button)
document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.pw-toggle').forEach(function (btn) {
        var input = btn.parentElement.querySelector('input');
        if (!input) return;
        btn.addEventListener('click', function () {
            var show = input.type === 'password';
            input.type = show ? 'text' : 'password';
            btn.setAttribute('aria-pressed', show ? 'true' : 'false');
            btn.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
            btn.querySelector('i').className = show ? 'fas fa-eye-slash' : 'fas fa-eye';
        });
    });
});

// Bottom toasts: auto-dismiss and close button
document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.toast').forEach(function (t) {
        function close() { t.classList.add('out'); setTimeout(function () { t.remove(); }, 300); }
        var x = t.querySelector('.toast-x');
        if (x) x.addEventListener('click', close);
        setTimeout(close, t.classList.contains('toast-error') ? 9000 : 6000);
    });
});
