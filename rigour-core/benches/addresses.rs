use criterion::{black_box, criterion_group, criterion_main, Criterion};
use rigour_core::addresses::normalize_address;

fn bench_normalize_short(c: &mut Criterion) {
    c.bench_function("normalize_address short", |b| {
        b.iter(|| normalize_address(black_box("123 Main St"), false, 4))
    });
}

fn bench_normalize_long(c: &mut Criterion) {
    c.bench_function("normalize_address long", |b| {
        b.iter(|| {
            normalize_address(
                black_box("Apartment 5B, 123 Main Street, Brooklyn, NY 11201"),
                false,
                4,
            )
        })
    });
}

fn bench_normalize_unicode(c: &mut Criterion) {
    c.bench_function("normalize_address unicode", |b| {
        b.iter(|| normalize_address(black_box("Квартира 5Б, улица Ленина, 123"), false, 4))
    });
}

criterion_group!(
    benches,
    bench_normalize_short,
    bench_normalize_long,
    bench_normalize_unicode
);
criterion_main!(benches);
