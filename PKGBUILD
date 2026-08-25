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
sha256sums=('bc85c600da322cfa822b585bf544995716d346490cc8ca4e9f4cfbe24f309e11')

package() {
    cd "$srcdir/$pkgname-$pkgver"
    install -dm755 "$pkgdir/usr/lib/$pkgname"
    cp -r pixelbuds_gui "$pkgdir/usr/lib/$pkgname/pixelbuds_gui"
    install -Dm755 packaging/pixelbuds-gui-launcher.sh "$pkgdir/usr/bin/$pkgname"
    install -Dm644 packaging/pixelbuds-gui.desktop "$pkgdir/usr/share/applications/$pkgname.desktop"
}
