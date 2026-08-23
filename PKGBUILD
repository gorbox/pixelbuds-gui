# Maintainer: pixelbuds-gui contributors
# AUR-style package for Arch / CachyOS. Uses the system python3 + pyside6.
#
# To install from a local clone of the repo:
#   makepkg -si
#
# To publish to the AUR, first replace the placeholder URL below with your
# real repo URL and provide a proper sha256sum (run `makepkg -g`).

pkgname=pixelbuds-gui
pkgver=0.1.0
pkgrel=1
pkgdesc="Desktop GUI to control Google Pixel Buds Pro on Linux"
arch=('any')
url="https://github.com/YOURNAME/pixelbuds-gui"
license=('MIT')
depends=('pbpctrl' 'pyside6')
source=("$pkgname-$pkgver.tar.gz::https://github.com/YOURNAME/$pkgname/archive/refs/tags/v$pkgver.tar.gz")
sha256sums=('SKIP')

package() {
    cd "$srcdir/$pkgname-$pkgver"
    install -dm755 "$pkgdir/usr/lib/$pkgname"
    cp -r pixelbuds_gui "$pkgdir/usr/lib/$pkgname/pixelbuds_gui"
    install -Dm755 packaging/pixelbuds-gui-launcher.sh "$pkgdir/usr/bin/$pkgname"
    install -Dm644 packaging/pixelbuds-gui.desktop "$pkgdir/usr/share/applications/$pkgname.desktop"
}
