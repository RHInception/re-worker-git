%if 0%{?rhel} && 0%{?rhel} <= 6
%{!?__python2: %global __python2 /usr/bin/python2}
%{!?python2_sitelib: %global python2_sitelib %(%{__python2} -c "from distutils.sysconfig import get_python_lib; print(get_python_lib())")}
%{!?python2_sitearch: %global python2_sitearch %(%{__python2} -c "from distutils.sysconfig import get_python_lib; print(get_python_lib(1))")}
%endif

%global _pkg_name replugin
%global _src_name reworkergit

Name: re-worker-git
Summary: Basic git worker for Release Engine
Version: 0.0.3
Release: 2%{?dist}

Group: Applications/System
License: AGPLv3
Source0: %{_src_name}-%{version}.tar.gz
Url: https://github.com/rhinception/re-worker-git

BuildArch: noarch
BuildRequires: python2-devel, python-setuptools
Requires: re-worker, python-requests, GitPython

%description
A basic Git worker for Winternewt which allows for merging and
history fixing.

%prep
%setup -q -n %{_src_name}-%{version}

%build
%{__python2} setup.py build

%install
%{__python2} setup.py install -O1 --root=$RPM_BUILD_ROOT --record=re-worker-git-files.txt

%files -f re-worker-git-files.txt
%defattr(-, root, root)
%doc README.md LICENSE AUTHORS
%dir %{python2_sitelib}/%{_pkg_name}
%exclude %{python2_sitelib}/%{_pkg_name}/__init__.py*


%changelog
* Fri Dec 12 2014 Steve Milner <stevem@gnulinux.net> - 0.0.3-2
- Fixed log entry in Merge.

* Fri Dec 12 2014 Steve Milner <stevem@gnulinux.net> - 0.0.3-1
- Merge added.

* Thu Oct 23 2014 Tim Bielawa <tbielawa@redhat.com> - 0.0.2-3
- Tell the FSM when we start

* Tue Oct 21 2014 Steve Milner <stevem@gnulinux.net> - 0.0.2-2
- More bug fixes.

* Tue Oct 21 2014 Steve Milner <stevem@gnulinux.net> - 0.0.2-1
- Bug fixes.

* Wed Oct 15 2014 Steve Milner <stevem@gnulinux.net> - 0.0.1-1
- Initial spec
