# Maintainer: gorbox <https://github.com/gorbox>
# AUR-style package for Arch / CachyOS. Uses the system python3 + pyside6.
#
# To install from a local clone of the repo:
#   makepkg -si

pkgname=pixelbuds-gui
pkgver=0.1.1
pkgrel=1
pkgdesc="Desktop GUI to control Google Pixel Buds Pro on Linux"
arch=('any')
url="https://github.com/gorbox/pixelbuds-gui"
license=('MIT')
depends=('pbpctrl' 'pyside6')
source=("$pkgname-$pkgver.tar.gz::https://github.com/gorbox/$pkgname/archive/refs/tags/v$pkgver.tar.gz")
sha256sums=('ae24c7d43c909e6d943424dfb73ca5fe6e67a8c2fc8558856491568c31517ec4')

package() {
    cd "$srcdir/$pkgname-$pkgver"
    install -dm755 "$pkgdir/usr/lib/$pkgname"
    cp -r pixelbuds_gui "$pkgdir/usr/lib/$pkgname/pixelbuds_gui"
    install -Dm755 packaging/pixelbuds-gui-launcher.sh "$pkgdir/usr/bin/$pkgname"
    install -Dm644 packaging/pixelbuds-gui.desktop "$pkgdir/usr/share/applications/$pkgname.desktop"
    for size in 16 24 32 48 64 128 256; do
        install -Dm644 "packaging/icons/hicolor/${size}x${size}/apps/pixelbuds-gui.png" \
            "$pkgdir/usr/share/icons/hicolor/${size}x${size}/apps/pixelbuds-gui.png"
    done
}
